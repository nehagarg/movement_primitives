import numpy as np


def canonical_system_alpha(goal_z, goal_t, start_t, int_dt=0.001):
    if goal_z <= 0.0:
        raise ValueError("Final phase must be > 0!")
    if start_t >= goal_t:
        raise ValueError("Goal must be chronologically after start!")

    execution_time = goal_t - start_t
    n_phases = int(execution_time / int_dt) + 1
    # assert that the execution_time is approximately divisible by int_dt
    assert abs(((n_phases - 1) * int_dt) - execution_time) < 0.05
    return (1.0 - goal_z ** (1.0 / (n_phases - 1))) * (n_phases - 1)


def phase(t, alpha, goal_t, start_t, int_dt=0.001, eps=1e-10):
    execution_time = goal_t - start_t
    b = max(1.0 - alpha * int_dt / execution_time, eps)
    return b ** ((t - start_t) / int_dt)


class ForcingTerm:
    def __init__(self, n_dims, n_weights_per_dim, goal_t, start_t, overlap, alpha_z):
        if n_weights_per_dim <= 0:
            raise ValueError("The number of weights per dimension must be > 1!")
        self.n_weights_per_dim = n_weights_per_dim
        if start_t >= goal_t:
            raise ValueError("Goal must be chronologically after start!")
        self.goal_t = goal_t
        self.start_t = start_t
        self.overlap = overlap
        self.alpha_z = alpha_z

        self._init_rbfs(n_dims, n_weights_per_dim, start_t)

    def _init_rbfs(self, n_dims, n_weights_per_dim, start_t):
        self.log_overlap = -np.log(self.overlap)
        self.execution_time = self.goal_t - self.start_t
        self.weights = np.zeros((n_dims, n_weights_per_dim))
        self.centers = np.empty(n_weights_per_dim)
        self.widths = np.empty(n_weights_per_dim)
        step = self.execution_time / (
                    self.n_weights_per_dim - 1)  # -1 because we want the last entry to be execution_time
        # do first iteration outside loop because we need access to i and i - 1 in loop
        t = start_t
        self.centers[0] = phase(t, self.alpha_z, self.goal_t, self.start_t)
        for i in range(1, self.n_weights_per_dim):
            t = i * step  # normally lower_border + i * step but lower_border is 0
            self.centers[i] = phase(t, self.alpha_z, self.goal_t, self.start_t)
            # Choose width of RBF basis functions automatically so that the
            # RBF centered at one center has value overlap at the next center
            diff = self.centers[i] - self.centers[i - 1]
            self.widths[i - 1] = self.log_overlap / diff ** 2
        # Width of last Gaussian cannot be calculated, just use the same width as the one before
        self.widths[self.n_weights_per_dim - 1] = self.widths[self.n_weights_per_dim - 2]

    def _activations(self, z, normalized):
        z = np.atleast_2d(z)  # 1 x n_steps
        squared_dist = (z - self.centers[:, np.newaxis]) ** 2
        activations = np.exp(-self.widths[:, np.newaxis] * squared_dist)
        if normalized:
            activations /= activations.sum(axis=0)
        return activations

    def __call__(self, t, int_dt=0.001):
        z = phase(t, self.alpha_z, self.goal_t, self.start_t, int_dt)
        z = np.atleast_1d(z)
        activations = self._activations(z, normalized=True)
        return z[np.newaxis, :] * self.weights.dot(activations)


def dmp_step(last_t, t, last_y, last_yd, goal_y, goal_yd, goal_ydd, start_y, start_yd, start_ydd, goal_t, start_t, alpha_y, beta_y, forcing_term, int_dt=0.001):
    if start_t >= goal_t:
        raise ValueError("Goal must be chronologically after start!")

    if t <= start_t:
        return np.copy(start_y), np.copy(start_yd), np.copy(start_ydd)

    execution_time = goal_t - start_t

    y = np.copy(last_y)
    yd = np.copy(last_yd)

    current_t = last_t
    while current_t < t:
        dt = int_dt
        if t - current_t < int_dt:
            dt = t - current_t
        current_t += dt

        f = forcing_term(current_t).squeeze()
        ydd = (alpha_y * (beta_y * (goal_y - last_y) + execution_time * goal_yd - execution_time * last_yd) + goal_ydd * execution_time ** 2 + f) / execution_time ** 2
        y += dt * last_yd
        yd += dt * ydd
    return y, yd


def dmp_open_loop(goal_t, start_t, dt, start_y, goal_y, alpha_y, beta_y, forcing_term):
    t = start_t
    y = np.copy(start_y)
    yd = np.zeros_like(y)
    T = [start_t]
    Y = [np.copy(y)]
    while t < goal_t:
        last_t = t
        t += dt
        y, yd = dmp_step(
            last_t, t, y, yd,
            goal_y=goal_y, goal_yd=np.zeros_like(goal_y), goal_ydd=np.zeros_like(goal_y),
            start_y=start_y, start_yd=np.zeros_like(start_y), start_ydd=np.zeros_like(start_y),
            goal_t=goal_t, start_t=start_t,
            alpha_y=alpha_y, beta_y=beta_y, forcing_term=forcing_term)
        T.append(t)
        Y.append(np.copy(y))
    return np.asarray(T), np.asarray(Y)