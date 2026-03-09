import numpy as np


def iaaft(x, n_iter=100):

    x = np.asarray(x, dtype=float)
    sorted_x = np.sort(x)

    # initial random shuffle
    y = np.random.permutation(x)

    for _ in range(n_iter):

        # enforce power spectrum
        Y = np.fft.rfft(y)
        phase = np.angle(Y)

        X = np.fft.rfft(x)
        Y = np.abs(X) * np.exp(1j * phase)

        y = np.fft.irfft(Y, n=len(x))

        # enforce amplitude distribution
        ranks = np.argsort(np.argsort(y))
        y = sorted_x[ranks]

    return y


def generate_surrogates(x, n=50):

    surrogates = []

    for i in range(n):
        surrogates.append(iaaft(x))

    return np.array(surrogates)
