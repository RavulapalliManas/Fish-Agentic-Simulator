import numpy as np
import cv2 as cv


class Fish_Agents:
    def __init__(self, id, pos, group_id, arena_center, size=8, speed_mean=1.5, speed_std=0.3):
        """
        Initialize a fish agent.
        
        Args:
            id: Unique identifier for this fish
            pos: Starting position [x, y] (defined globally)
            group_id: Which group this fish belongs to
            arena_center: (x, y) center of arena for center attraction
            size: Radius of the dot in pixels
            speed_mean: Mean speed (pixels/frame) - sampled from Gaussian
            speed_std: Standard deviation for speed
        """
        self.id = id
        self.group_id = group_id
        self.size = size
        self.arena_center = np.array(arena_center, dtype=float)
        
        # Sample speed from Gaussian distribution for biological variation
        self.max_speed = np.abs(np.random.normal(speed_mean, speed_std))
        
        # Position and velocity (position passed in from global config)
        self.pos = np.array(pos, dtype=float)
        self.vel = self._random_velocity()
        
        # Behavioral parameters
        self.max_force = 0.3  # Maximum steering force
        self.max_turn_angle = np.pi / 12  # ~15 degrees max turn per frame
        
        # Perception radii
        self.neighbor_radius = 100  # How far fish can see neighbors
        self.separation_radius = 25  # Personal space
        
        # Behavioral weights (tunable for different behaviors)
        self.cohesion_weight = 1.0      # Attraction to group center (reduced)
        self.alignment_weight = 1.2     # Match neighbor velocities
        self.separation_weight = 2.5    # Avoid crowding (increased)
        self.noise_weight = 0.5         # Random exploration (increased for individuality)
        self.wall_avoidance_weight = 3.0  # Stay away from edges
        self.center_attraction_weight = 0.8  # Keep near arena center (reduced)
        
        # Individual random bias for each fish (Gaussian component)
        self.random_bias_angle = np.random.uniform(0, 2 * np.pi)
        self.random_bias_change_rate = 0.02  # How fast bias angle changes
        
    def _random_velocity(self):
        """Generate a random initial velocity."""
        angle = np.random.uniform(0, 2 * np.pi)
        speed = np.random.uniform(0.3, 0.7) * self.max_speed
        return np.array([np.cos(angle) * speed, np.sin(angle) * speed])
    
    def update(self, neighbors, arena_size, goal_position=None):
        """
        Update fish position based on boid rules and goal.
        
        Args:
            neighbors: List of nearby Fish_Agents
            arena_size: (width, height) of the arena (passed in from global)
            goal_position: Optional target position [x, y] for directed movement
        """
        # Calculate steering forces
        acceleration = np.zeros(2)
        
        # Boid rules (only if there are neighbors)
        if len(neighbors) > 0:
            acceleration += self.cohesion(neighbors) * self.cohesion_weight
            acceleration += self.alignment(neighbors) * self.alignment_weight
            acceleration += self.separation(neighbors) * self.separation_weight
        
        # Center attraction - keeps fish near arena center
        acceleration += self.seek_center() * self.center_attraction_weight
        
        # Add goal-seeking behavior (for splits - not used for group swimming)
        if goal_position is not None:
            acceleration += self.seek_goal(goal_position) * 0.5
        
        # Add random noise for natural movement
        acceleration += self.random_noise() * self.noise_weight
        
        # Wall avoidance (arena_size passed in)
        acceleration += self.avoid_walls(arena_size) * self.wall_avoidance_weight
        
        # Limit acceleration to max force
        acc_magnitude = np.linalg.norm(acceleration)
        if acc_magnitude > self.max_force:
            acceleration = (acceleration / acc_magnitude) * self.max_force
        
        # Apply turning angle constraint for smooth, realistic turns
        self.vel = self._constrain_turn(self.vel, acceleration)
        
        # Update velocity and limit speed
        self.vel += acceleration
        speed = np.linalg.norm(self.vel)
        if speed > self.max_speed:
            self.vel = (self.vel / speed) * self.max_speed
        elif speed < 0.5:  # Minimum speed to keep moving (increased)
            if speed > 0:
                self.vel = (self.vel / speed) * 0.5
            else:
                # If stopped, give it a random push
                angle = np.random.uniform(0, 2 * np.pi)
                self.vel = np.array([np.cos(angle) * 0.5, np.sin(angle) * 0.5])
        
        # Update position
        self.pos += self.vel
        
        # Keep within bounds (hard constraint)
        self.pos[0] = np.clip(self.pos[0], 0, arena_size[0])
        self.pos[1] = np.clip(self.pos[1], 0, arena_size[1])
    
    def _constrain_turn(self, current_vel, acceleration):
        """Limit the turning angle to be biologically plausible."""
        speed = np.linalg.norm(current_vel)
        if speed < 0.01:
            return current_vel
        
        desired_vel = current_vel + acceleration
        
        # Calculate angle between current and desired direction
        current_angle = np.arctan2(current_vel[1], current_vel[0])
        desired_angle = np.arctan2(desired_vel[1], desired_vel[0])
        
        angle_diff = desired_angle - current_angle
        # Normalize to [-pi, pi]
        angle_diff = np.arctan2(np.sin(angle_diff), np.cos(angle_diff))
        
        # Constrain the turn to max_turn_angle
        if abs(angle_diff) > self.max_turn_angle:
            angle_diff = np.sign(angle_diff) * self.max_turn_angle
        
        new_angle = current_angle + angle_diff
        
        return np.array([np.cos(new_angle) * speed, np.sin(new_angle) * speed])
    
    def cohesion(self, neighbors):
        """Steer towards the average position of neighbors (group attraction)."""
        if len(neighbors) == 0:
            return np.zeros(2)
        
        center = np.mean([n.pos for n in neighbors], axis=0)
        desired = center - self.pos
        
        dist = np.linalg.norm(desired)
        if dist > 0:
            desired = (desired / dist) * self.max_speed
            return desired - self.vel
        return np.zeros(2)
    
    def alignment(self, neighbors):
        """Steer towards the average heading of neighbors (velocity matching)."""
        if len(neighbors) == 0:
            return np.zeros(2)
        
        avg_vel = np.mean([n.vel for n in neighbors], axis=0)
        
        speed = np.linalg.norm(avg_vel)
        if speed > 0:
            avg_vel = (avg_vel / speed) * self.max_speed
            return avg_vel - self.vel
        return np.zeros(2)
    
    def separation(self, neighbors):
        """Avoid crowding neighbors (personal space)."""
        steer = np.zeros(2)
        count = 0
        
        for other in neighbors:
            dist = np.linalg.norm(self.pos - other.pos)
            if 0 < dist < self.separation_radius:
                # Direction away from neighbor
                diff = self.pos - other.pos
                # Weight by inverse square of distance (closer = stronger repulsion)
                diff = diff / (dist ** 2)
                steer += diff
                count += 1
        
        if count > 0:
            steer = steer / count
            magnitude = np.linalg.norm(steer)
            if magnitude > 0:
                steer = (steer / magnitude) * self.max_speed
                steer = steer - self.vel
        
        return steer
    
    def seek_center(self):
        """Keep fish group near the center of arena (subtle attraction)."""
        desired = self.arena_center - self.pos
        dist = np.linalg.norm(desired)
        
        # Only apply if fish is getting far from center
        if dist > 150:  # Start pulling back after 150 pixels from center
            if dist > 0:
                # Strength increases with distance
                strength = min((dist - 150) / 200, 1.0)
                desired = (desired / dist) * self.max_speed * strength
                return desired - self.vel
        return np.zeros(2)
    
    def seek_goal(self, goal_position):
        """Steer towards a goal position (for split scenarios)."""
        desired = np.array(goal_position) - self.pos
        dist = np.linalg.norm(desired)
        
        if dist > 0:
            # Slow down as we approach the goal
            if dist < 100:
                desired = (desired / dist) * self.max_speed * (dist / 100)
            else:
                desired = (desired / dist) * self.max_speed
            
            return desired - self.vel
        return np.zeros(2)
    
    def random_noise(self):
        """Add random perturbation for natural, non-robotic movement with individual bias."""
        # Update the random bias angle slowly (creates persistent random direction)
        self.random_bias_angle += np.random.randn() * self.random_bias_change_rate
        
        # Combine random walk with persistent bias
        random_component = np.array([
            np.cos(self.random_bias_angle),
            np.sin(self.random_bias_angle)
        ]) * 0.4  # Persistent bias
        
        # Add some purely random component
        pure_random_angle = np.random.uniform(0, 2 * np.pi)
        pure_random = np.array([
            np.cos(pure_random_angle),
            np.sin(pure_random_angle)
        ]) * np.random.uniform(0, 0.3)
        
        return random_component + pure_random
    
    def avoid_walls(self, arena_size):
        """Steer away from arena boundaries."""
        steer = np.zeros(2)
        margin = 80  # Distance from wall to start avoiding
        strength = 2.0  # How strong the avoidance force is
        
        # Left wall
        if self.pos[0] < margin:
            steer[0] += strength * (margin - self.pos[0]) / margin
        # Right wall
        if self.pos[0] > arena_size[0] - margin:
            steer[0] -= strength * (self.pos[0] - (arena_size[0] - margin)) / margin
        # Top wall
        if self.pos[1] < margin:
            steer[1] += strength * (margin - self.pos[1]) / margin
        # Bottom wall
        if self.pos[1] > arena_size[1] - margin:
            steer[1] -= strength * (self.pos[1] - (arena_size[1] - margin)) / margin
        
        return steer
    
    def get_neighbors(self, all_agents):
        """Find nearby agents of the same group within perception radius."""
        neighbors = []
        for other in all_agents:
            if other.id != self.id and other.group_id == self.group_id:
                dist = np.linalg.norm(self.pos - other.pos)
                if dist < self.neighbor_radius:
                    neighbors.append(other)
        return neighbors
    
    def get_state(self):
        """Return current state as a dictionary (for data logging)."""
        return {
            'id': self.id,
            'group_id': self.group_id,
            'pos_x': float(self.pos[0]),
            'pos_y': float(self.pos[1]),
            'vel_x': float(self.vel[0]),
            'vel_y': float(self.vel[1]),
            'speed': float(np.linalg.norm(self.vel)),
            'heading': float(np.arctan2(self.vel[1], self.vel[0]))
        }