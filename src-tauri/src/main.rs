#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

use dirs::download_dir;
use serde::Serialize;
use std::{
    net::TcpListener,
    path::{Path, PathBuf},
    process::{Child, Command, Stdio},
    sync::Mutex,
};
use tauri::{AppHandle, Manager, State};

#[derive(Default)]
struct BackendState {
    process: Mutex<Option<Child>>,
    port: Mutex<u16>,
    startup_error: Mutex<Option<String>>,
}

#[derive(Serialize)]
#[serde(rename_all = "camelCase")]
struct BackendInfo {
    base_url: String,
    default_output_path: String,
    startup_error: Option<String>,
}

#[tauri::command]
fn get_backend_info(state: State<'_, BackendState>) -> Result<BackendInfo, String> {
    let port = *state
        .port
        .lock()
        .map_err(|_| String::from("Unable to read backend state"))?;
    let startup_error = state
        .startup_error
        .lock()
        .map_err(|_| String::from("Unable to read backend error state"))?
        .clone();
    let output_dir = default_output_path().map_err(|error| error.to_string())?;

    Ok(BackendInfo {
        base_url: format!("http://127.0.0.1:{port}"),
        default_output_path: output_dir.to_string_lossy().to_string(),
        startup_error,
    })
}

fn main() {
    let app = tauri::Builder::default()
        .manage(BackendState::default())
        .setup(|app| {
            if let Err(error) = spawn_backend(app.handle()) {
                let error_message = error.to_string();
                let state = app.state::<BackendState>();
                let startup_error_lock = state.startup_error.lock();
                if let Ok(mut startup_error) = startup_error_lock {
                    *startup_error = Some(error_message);
                }
            }
            Ok(())
        })
        .invoke_handler(tauri::generate_handler![get_backend_info])
        .build(tauri::generate_context!())
        .expect("failed to build tauri application");

    let handle = app.handle().clone();
    app.run(move |_handle, event| {
        if let tauri::RunEvent::Exit = event {
            shutdown_backend(&handle);
        }
    });
}

fn spawn_backend(app: &AppHandle) -> Result<(), Box<dyn std::error::Error>> {
    let state = app.state::<BackendState>();
    let port = pick_free_port()?;

    let mut command = if cfg!(debug_assertions) {
        backend_dev_command(port)
    } else {
        backend_packaged_command(app, port)?
    };

    let child = command
        .stdout(Stdio::null())
        .stderr(Stdio::null())
        .spawn()?;

    if let Ok(mut stored_port) = state.port.lock() {
        *stored_port = port;
    }
    if let Ok(mut startup_error) = state.startup_error.lock() {
        *startup_error = None;
    }
    if let Ok(mut process) = state.process.lock() {
        *process = Some(child);
    }
    Ok(())
}

fn shutdown_backend(app: &AppHandle) {
    let state = app.state::<BackendState>();
    let mut process = match state.process.lock() {
        Ok(process) => process,
        Err(_) => return,
    };

    if let Some(mut child) = process.take() {
        let _ = child.kill();
        let _ = child.wait();
    }
}

fn pick_free_port() -> Result<u16, std::io::Error> {
    let listener = TcpListener::bind(("127.0.0.1", 0))?;
    let port = listener.local_addr()?.port();
    drop(listener);
    Ok(port)
}

fn backend_dev_command(port: u16) -> Command {
    let python = if cfg!(target_os = "windows") {
        "python"
    } else {
        "python3"
    };

    let script_path = std::env::current_dir()
        .unwrap_or_else(|_| PathBuf::from("."))
        .join("backend")
        .join("main.py");

    let mut command = Command::new(python);
    command
        .arg(script_path)
        .arg("--host")
        .arg("127.0.0.1")
        .arg("--port")
        .arg(port.to_string());
    command
}

fn backend_packaged_command(
    app: &AppHandle,
    port: u16,
) -> Result<Command, Box<dyn std::error::Error>> {
    let executable_name = if cfg!(target_os = "windows") {
        "fish-backend.exe"
    } else {
        "fish-backend"
    };

    let resource_dir = app.path().resource_dir()?;
    let executable_path = resolve_packaged_backend_path(&resource_dir, executable_name)
        .ok_or_else(|| format!("Bundled backend executable not found in {}", resource_dir.display()))?;

    let mut command = Command::new(executable_path);
    command
        .arg("--host")
        .arg("127.0.0.1")
        .arg("--port")
        .arg(port.to_string());
    Ok(command)
}

fn default_output_path() -> Result<PathBuf, std::io::Error> {
    let base_dir = download_dir()
        .or_else(|| std::env::current_dir().ok())
        .unwrap_or_else(|| PathBuf::from("."));
    Ok(base_dir.join("fish-stimulus.mp4"))
}

fn resolve_packaged_backend_path(resource_dir: &Path, executable_name: &str) -> Option<PathBuf> {
    let direct = resource_dir
        .join("backend")
        .join("dist")
        .join("fish-backend")
        .join(executable_name);
    if direct.exists() {
        return Some(direct);
    }

    let tauri_resource = resource_dir
        .join("_up_")
        .join("backend")
        .join("dist")
        .join("fish-backend")
        .join(executable_name);
    if tauri_resource.exists() {
        return Some(tauri_resource);
    }

    None
}
