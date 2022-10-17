# -*- coding: utf-8 -*-
import numpy as np

from qibo.config import PRECISION_TOL


def shannon_entropy(probability_array, base: float = 2):
    """Calculate the Shannon entropy of a probability array :math:`\\mathbf{p}`, which is given by

    ..math::
        H(\\mathbf{p}) \\coloneqq - \\sum_{k = 0}^{d^{2} - 1} \\, p_{k} \\, \\log_{b}(p_{k}) \\, ,

    where :math:`d = \\text{dim}(\\mathcal{H})` is the dimension of the Hilbert space :math:`\\mathcal{H}`,
    :math:`b` is the log base (default 2), and :math:`0 \\log_{b}(0) \\equiv 0`.

    Args:
        probability_array: a probability vector :math:`\\mathbf{p}`.
        base: the base of the log. Default: 2.

    Returns:
        The Shannon entropy :math:`H(\\mathcal{p})`.

    """

    if base < 0:
        raise ValueError("log base must be non-negative.")

    if len(probability_array.shape) != 1:
        raise TypeError(
            f"Probability array must have dims (k,) but it has {probability_array.shape}."
        )

    if len(probability_array) == 0:
        raise TypeError("Empty array.")

    if any(probability_array) < 0 or any(probability_array) > 1.0:
        raise ValueError(
            "All elements of the probability array must be between 0. and 1.."
        )

    if (np.sum(probability_array) > 1.0 + PRECISION_TOL) or (np.sum(probability_array) < 1. - PRECISION_TOL):
        raise ValueError("Probability vector must sum to 1.")

    if base == 2:
        log_prob = (
            np.asarray([0.0 if p == 0.0 else np.log2(p) for p in probability_array])
            if any(probability_array == 0.0)
            else np.log2(probability_array)
        )
    elif base == 10:
        log_prob = (
            np.asarray([0.0 if p == 0.0 else np.log10(p) for p in probability_array])
            if any(probability_array == 0.0)
            else np.log(probability_array)
        )
    elif base == np.e:
        log_prob = (
            np.asarray([0.0 if p == 0.0 else np.log(p) for p in probability_array])
            if any(probability_array == 0.0)
            else np.log(probability_array)
        )
    else:
        log_prob = (
            np.asarray(
                [
                    0.0 if p == 0.0 else np.log(p) / np.log(base)
                    for p in probability_array
                ]
            )
            if any(probability_array == 0.0)
            else np.log(probability_array) / np.log(base)
        )
    
    entropy = -np.sum(probability_array * log_prob)

    # absolute value if entropy == 0.0 to avoid returning -0.0
    entropy = np.abs(entropy) if entropy == 0.0 else entropy

    return entropy
