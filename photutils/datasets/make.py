# Licensed under a 3-clause BSD style license - see LICENSE.rst
"""
This module provides tools for making example datasets for examples and
tests.
"""

import warnings

import astropy.units as u
import numpy as np
from astropy import coordinates as coord
from astropy.convolution import discretize_model
from astropy.io import fits
from astropy.modeling import models
from astropy.nddata import overlap_slices
from astropy.table import QTable
from astropy.utils.exceptions import AstropyUserWarning
from astropy.wcs import WCS

from photutils.psf import IntegratedGaussianPRF
from photutils.utils._misc import _get_version_info
from photutils.utils._progress_bars import add_progress_bar

__all__ = ['apply_poisson_noise', 'make_noise_image',
           'make_random_models_table', 'make_random_gaussians_table',
           'make_model_sources_image', 'make_gaussian_sources_image',
           'make_4gaussians_image', 'make_100gaussians_image',
           'make_wcs', 'make_gwcs', 'make_imagehdu',
           'make_gaussian_prf_sources_image',
           'make_test_psf_data']

__doctest_requires__ = {('make_gwcs'): ['gwcs']}


def apply_poisson_noise(data, seed=None):
    """
    Apply Poisson noise to an array, where the value of each element in
    the input array represents the expected number of counts.

    Each pixel in the output array is generated by drawing a random
    sample from a Poisson distribution whose expectation value is given
    by the pixel value in the input array.

    Parameters
    ----------
    data : array_like
        The array on which to apply Poisson noise.  Every pixel in the
        array must have a positive value (i.e., counts).

    seed : int, optional
        A seed to initialize the `numpy.random.BitGenerator`. If `None`,
        then fresh, unpredictable entropy will be pulled from the OS.

    Returns
    -------
    result : `~numpy.ndarray`
        The data array after applying Poisson noise.

    See Also
    --------
    make_noise_image

    Examples
    --------
    .. plot::
        :include-source:

        import matplotlib.pyplot as plt
        from photutils.datasets import (apply_poisson_noise,
                                        make_4gaussians_image)

        data1 = make_4gaussians_image(noise=False)
        data2 = apply_poisson_noise(data1, seed=0)

        # plot the images
        fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(8, 8))
        ax1.imshow(data1, origin='lower', interpolation='nearest')
        ax1.set_title('Original image')
        ax2.imshow(data2, origin='lower', interpolation='nearest')
        ax2.set_title('Original image with Poisson noise applied')
    """
    data = np.asanyarray(data)
    if np.any(data < 0):
        raise ValueError('data must not contain any negative values')

    rng = np.random.default_rng(seed)

    return rng.poisson(data)


def make_noise_image(shape, distribution='gaussian', mean=None, stddev=None,
                     seed=None):
    r"""
    Make a noise image containing Gaussian or Poisson noise.

    Parameters
    ----------
    shape : 2-tuple of int
        The shape of the output 2D image.

    distribution : {'gaussian', 'poisson'}
        The distribution used to generate the random noise:

            * ``'gaussian'``: Gaussian distributed noise.
            * ``'poisson'``: Poisson distributed noise.

    mean : float
        The mean of the random distribution.  Required for both Gaussian
        and Poisson noise.  The default is 0.

    stddev : float, optional
        The standard deviation of the Gaussian noise to add to the
        output image.  Required for Gaussian noise and ignored for
        Poisson noise (the variance of the Poisson distribution is equal
        to its mean).

    seed : int, optional
        A seed to initialize the `numpy.random.BitGenerator`. If `None`,
        then fresh, unpredictable entropy will be pulled from the OS.

    Returns
    -------
    image : 2D `~numpy.ndarray`
        Image containing random noise.

    See Also
    --------
    apply_poisson_noise

    Examples
    --------
    .. plot::
        :include-source:

        import matplotlib.pyplot as plt
        from photutils.datasets import make_noise_image

        # make Gaussian and Poisson noise images
        shape = (100, 100)
        image1 = make_noise_image(shape, distribution='gaussian', mean=0.,
                                  stddev=5.)
        image2 = make_noise_image(shape, distribution='poisson', mean=5.)

        # plot the images
        fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(8, 4))
        ax1.imshow(image1, origin='lower', interpolation='nearest')
        ax1.set_title(r'Gaussian noise ($\mu=0$, $\sigma=5.$)')
        ax2.imshow(image2, origin='lower', interpolation='nearest')
        ax2.set_title(r'Poisson noise ($\mu=5$)')
    """
    if mean is None:
        raise ValueError('"mean" must be input')

    rng = np.random.default_rng(seed)

    if distribution == 'gaussian':
        if stddev is None:
            raise ValueError('"stddev" must be input for Gaussian noise')
        image = rng.normal(loc=mean, scale=stddev, size=shape)
    elif distribution == 'poisson':
        image = rng.poisson(lam=mean, size=shape)
    else:
        raise ValueError(f'Invalid distribution: {distribution}. Use either '
                         '"gaussian" or "poisson".')

    return image


def make_random_models_table(n_sources, param_ranges, seed=None):
    """
    Make a `~astropy.table.QTable` containing randomly generated
    parameters for an Astropy model to simulate a set of sources.

    Each row of the table corresponds to a source whose parameters are
    defined by the column names.  The parameters are drawn from a
    uniform distribution over the specified input ranges.

    The output table can be input into :func:`make_model_sources_image`
    to create an image containing the model sources.

    Parameters
    ----------
    n_sources : float
        The number of random model sources to generate.

    param_ranges : dict
        The lower and upper boundaries for each of the model parameters
        as a dictionary mapping the parameter name to its ``(lower,
        upper)`` bounds.

    seed : int, optional
        A seed to initialize the `numpy.random.BitGenerator`. If `None`,
        then fresh, unpredictable entropy will be pulled from the OS.

    Returns
    -------
    table : `~astropy.table.QTable`
        A table of parameters for the randomly generated sources.  Each
        row of the table corresponds to a source whose model parameters
        are defined by the column names.  The column names will be the
        keys of the dictionary ``param_ranges``.

    See Also
    --------
    make_random_gaussians_table, make_model_sources_image

    Notes
    -----
    To generate identical parameter values from separate function
    calls, ``param_ranges`` must have the same parameter ranges and the
    ``seed`` must be the same.

    Examples
    --------
    >>> from photutils.datasets import make_random_models_table
    >>> n_sources = 5
    >>> param_ranges = {'amplitude': [500, 1000],
    ...                 'x_mean': [0, 500],
    ...                 'y_mean': [0, 300],
    ...                 'x_stddev': [1, 5],
    ...                 'y_stddev': [1, 5],
    ...                 'theta': [0, np.pi]}
    >>> sources = make_random_models_table(n_sources, param_ranges,
    ...                                    seed=0)
    >>> for col in sources.colnames:
    ...     sources[col].info.format = '%.8g'  # for consistent table output
    >>> print(sources)
    amplitude   x_mean    y_mean    x_stddev  y_stddev   theta
    --------- --------- ---------- --------- --------- ---------
    818.48084 456.37779  244.75607 1.7026225 1.1132787 1.2053586
    634.89336 303.31789 0.82155005 4.4527157 1.4971331 3.1328274
    520.48676 364.74828  257.22128 3.1658449 3.6824977 3.0813851
    508.26382  271.8125  10.075673 2.1988476  3.588758 2.1536937
    906.63512 467.53621  218.89663 2.6907489 3.4615404 2.0434781
    """
    rng = np.random.default_rng(seed)

    meta = {'version': _get_version_info()}
    sources = QTable()
    sources.meta.update(meta)  # keep sources.meta type
    for param_name, (lower, upper) in param_ranges.items():
        # Generate a column for every item in param_ranges, even if it
        # is not in the model (e.g., flux). However, such columns will be
        # ignored when rendering the image.
        sources[param_name] = rng.uniform(lower, upper, n_sources)

    return sources


def make_random_gaussians_table(n_sources, param_ranges, seed=None):
    """
    Make a `~astropy.table.QTable` containing randomly generated
    parameters for 2D Gaussian sources.

    Each row of the table corresponds to a Gaussian source whose
    parameters are defined by the column names.  The parameters are
    drawn from a uniform distribution over the specified input ranges.

    The output table can be input into
    :func:`make_gaussian_sources_image` to create an image containing
    the 2D Gaussian sources.

    Parameters
    ----------
    n_sources : float
        The number of random Gaussian sources to generate.

    param_ranges : dict
        The lower and upper boundaries for each of the
        `~astropy.modeling.functional_models.Gaussian2D` parameters
        as a dictionary mapping the parameter name to its ``(lower,
        upper)`` bounds. The dictionary keys must be valid
        `~astropy.modeling.functional_models.Gaussian2D` parameter
        names or ``'flux'``. If ``'flux'`` is specified, but not
        ``'amplitude'`` then the 2D Gaussian amplitudes will be
        calculated and placed in the output table. If both ``'flux'``
        and ``'amplitude'`` are specified, then ``'flux'`` will be
        ignored. Model parameters not defined in ``param_ranges`` will
        be set to the default value.

    seed : int, optional
        A seed to initialize the `numpy.random.BitGenerator`. If `None`,
        then fresh, unpredictable entropy will be pulled from the OS.

    Returns
    -------
    table : `~astropy.table.QTable`
        A table of parameters for the randomly generated Gaussian
        sources.  Each row of the table corresponds to a Gaussian source
        whose parameters are defined by the column names.

    See Also
    --------
    make_random_models_table, make_gaussian_sources_image

    Notes
    -----
    To generate identical parameter values from separate function
    calls, ``param_ranges`` must have the same parameter ranges and the
    ``seed`` must be the same.

    Examples
    --------
    >>> from photutils.datasets import make_random_gaussians_table
    >>> n_sources = 5
    >>> param_ranges = {'amplitude': [500, 1000],
    ...                 'x_mean': [0, 500],
    ...                 'y_mean': [0, 300],
    ...                 'x_stddev': [1, 5],
    ...                 'y_stddev': [1, 5],
    ...                 'theta': [0, np.pi]}
    >>> sources = make_random_gaussians_table(n_sources, param_ranges,
    ...                                       seed=0)
    >>> for col in sources.colnames:
    ...     sources[col].info.format = '%.8g'  # for consistent table output
    >>> print(sources)
    amplitude   x_mean    y_mean    x_stddev  y_stddev   theta
    --------- --------- ---------- --------- --------- ---------
    818.48084 456.37779  244.75607 1.7026225 1.1132787 1.2053586
    634.89336 303.31789 0.82155005 4.4527157 1.4971331 3.1328274
    520.48676 364.74828  257.22128 3.1658449 3.6824977 3.0813851
    508.26382  271.8125  10.075673 2.1988476  3.588758 2.1536937
    906.63512 467.53621  218.89663 2.6907489 3.4615404 2.0434781

    To specifying the flux range instead of the amplitude range:

    >>> param_ranges = {'flux': [500, 1000],
    ...                 'x_mean': [0, 500],
    ...                 'y_mean': [0, 300],
    ...                 'x_stddev': [1, 5],
    ...                 'y_stddev': [1, 5],
    ...                 'theta': [0, np.pi]}
    >>> sources = make_random_gaussians_table(n_sources, param_ranges,
    ...                                       seed=0)
    >>> for col in sources.colnames:
    ...     sources[col].info.format = '%.8g'  # for consistent table output
    >>> print(sources)
       flux     x_mean    y_mean    x_stddev  y_stddev   theta   amplitude
    --------- --------- ---------- --------- --------- --------- ---------
    818.48084 456.37779  244.75607 1.7026225 1.1132787 1.2053586 68.723678
    634.89336 303.31789 0.82155005 4.4527157 1.4971331 3.1328274 15.157778
    520.48676 364.74828  257.22128 3.1658449 3.6824977 3.0813851 7.1055501
    508.26382  271.8125  10.075673 2.1988476  3.588758 2.1536937 10.251089
    906.63512 467.53621  218.89663 2.6907489 3.4615404 2.0434781 15.492093

    Note that in this case the output table contains both a flux and
    amplitude column.  The flux column will be ignored when generating
    an image of the models using :func:`make_gaussian_sources_image`.
    """
    sources = make_random_models_table(n_sources, param_ranges,
                                       seed=seed)

    # convert Gaussian2D flux to amplitude
    if 'flux' in param_ranges and 'amplitude' not in param_ranges:
        model = models.Gaussian2D(x_stddev=1, y_stddev=1)

        if 'x_stddev' in sources.colnames:
            xstd = sources['x_stddev']
        else:
            xstd = model.x_stddev.value  # default
        if 'y_stddev' in sources.colnames:
            ystd = sources['y_stddev']
        else:
            ystd = model.y_stddev.value  # default

        sources = sources.copy()
        sources['amplitude'] = sources['flux'] / (2.0 * np.pi * xstd * ystd)

    return sources


def make_model_sources_image(shape, model, source_table, oversample=1):
    """
    Make an image containing sources generated from a user-specified
    model.

    Parameters
    ----------
    shape : 2-tuple of int
        The shape of the output 2D image.

    model : 2D astropy.modeling.models object
        The model to be used for rendering the sources.

    source_table : `~astropy.table.Table`
        Table of parameters for the sources.  Each row of the table
        corresponds to a source whose model parameters are defined by
        the column names, which must match the model parameter names.
        Column names that do not match model parameters will be ignored.
        Model parameters not defined in the table will be set to the
        ``model`` default value.

    oversample : float, optional
        The sampling factor used to discretize the models on a pixel
        grid.  If the value is 1.0 (the default), then the models will
        be discretized by taking the value at the center of the pixel
        bin.  Note that this method will not preserve the total flux of
        very small sources.  Otherwise, the models will be discretized
        by taking the average over an oversampled grid.  The pixels will
        be oversampled by the ``oversample`` factor.

    Returns
    -------
    image : 2D `~numpy.ndarray`
        Image containing model sources.

    See Also
    --------
    make_random_models_table, make_gaussian_sources_image

    Examples
    --------
    .. plot::
        :include-source:

        import matplotlib.pyplot as plt
        from astropy.modeling.models import Moffat2D
        from photutils.datasets import (make_model_sources_image,
                                        make_random_models_table)

        model = Moffat2D()
        n_sources = 10
        shape = (100, 100)
        param_ranges = {'amplitude': [100, 200],
                        'x_0': [0, shape[1]],
                        'y_0': [0, shape[0]],
                        'gamma': [5, 10],
                        'alpha': [1, 2]}
        sources = make_random_models_table(n_sources, param_ranges,
                                           seed=0)

        data = make_model_sources_image(shape, model, sources)
        plt.imshow(data)
    """
    image = np.zeros(shape, dtype=float)
    yidx, xidx = np.indices(shape)

    params_to_set = []
    for param in source_table.colnames:
        if param in model.param_names:
            params_to_set.append(param)

    # Save the initial parameter values so we can set them back when
    # done with the loop. It's best not to copy a model, because some
    # models (e.g., PSF models) may have substantial amounts of data in
    # them.
    init_params = {param: getattr(model, param) for param in params_to_set}

    try:
        for source in source_table:
            for param in params_to_set:
                setattr(model, param, source[param])

            if oversample == 1:
                image += model(xidx, yidx)
            else:
                image += discretize_model(model, (0, shape[1]),
                                          (0, shape[0]), mode='oversample',
                                          factor=oversample)
    finally:
        for param, value in init_params.items():
            setattr(model, param, value)

    return image


def make_gaussian_sources_image(shape, source_table, oversample=1):
    r"""
    Make an image containing 2D Gaussian sources.

    Parameters
    ----------
    shape : 2-tuple of int
        The shape of the output 2D image.

    source_table : `~astropy.table.Table`
        Table of parameters for the Gaussian sources.  Each row of the
        table corresponds to a Gaussian source whose parameters are
        defined by the column names.  With the exception of ``'flux'``,
        column names that do not match model parameters will be ignored
        (flux will be converted to amplitude).  If both ``'flux'`` and
        ``'amplitude'`` are present, then ``'flux'`` will be ignored.
        Model parameters not defined in the table will be set to the
        default value.

    oversample : float, optional
        The sampling factor used to discretize the models on a pixel
        grid.  If the value is 1.0 (the default), then the models will
        be discretized by taking the value at the center of the pixel
        bin.  Note that this method will not preserve the total flux of
        very small sources.  Otherwise, the models will be discretized
        by taking the average over an oversampled grid.  The pixels will
        be oversampled by the ``oversample`` factor.

    Returns
    -------
    image : 2D `~numpy.ndarray`
        Image containing 2D Gaussian sources.

    See Also
    --------
    make_model_sources_image, make_random_gaussians_table

    Examples
    --------
    .. plot::
        :include-source:

        import matplotlib.pyplot as plt
        import numpy as np
        from astropy.table import QTable
        from photutils.datasets import (make_gaussian_sources_image,
                                        make_noise_image)

        # make a table of Gaussian sources
        table = QTable()
        table['amplitude'] = [50, 70, 150, 210]
        table['x_mean'] = [160, 25, 150, 90]
        table['y_mean'] = [70, 40, 25, 60]
        table['x_stddev'] = [15.2, 5.1, 3., 8.1]
        table['y_stddev'] = [2.6, 2.5, 3., 4.7]
        table['theta'] = np.radians(np.array([145., 20., 0., 60.]))

        # make an image of the sources without noise, with Gaussian
        # noise, and with Poisson noise
        shape = (100, 200)
        image1 = make_gaussian_sources_image(shape, table)
        image2 = image1 + make_noise_image(shape, distribution='gaussian',
                                           mean=5., stddev=5.)
        image3 = image1 + make_noise_image(shape, distribution='poisson',
                                           mean=5.)

        # plot the images
        fig, (ax1, ax2, ax3) = plt.subplots(3, 1, figsize=(8, 12))
        ax1.imshow(image1, origin='lower', interpolation='nearest')
        ax1.set_title('Original image')
        ax2.imshow(image2, origin='lower', interpolation='nearest')
        ax2.set_title('Original image with added Gaussian noise'
                      r' ($\mu = 5, \sigma = 5$)')
        ax3.imshow(image3, origin='lower', interpolation='nearest')
        ax3.set_title(r'Original image with added Poisson noise ($\mu = 5$)')
    """
    model = models.Gaussian2D(x_stddev=1, y_stddev=1)

    if 'x_stddev' in source_table.colnames:
        xstd = source_table['x_stddev']
    else:
        xstd = model.x_stddev.value  # default
    if 'y_stddev' in source_table.colnames:
        ystd = source_table['y_stddev']
    else:
        ystd = model.y_stddev.value  # default

    colnames = source_table.colnames
    if 'flux' in colnames and 'amplitude' not in colnames:
        source_table = source_table.copy()
        source_table['amplitude'] = (source_table['flux']
                                     / (2.0 * np.pi * xstd * ystd))

    return make_model_sources_image(shape, model, source_table,
                                    oversample=oversample)


def make_gaussian_prf_sources_image(shape, source_table):
    r"""
    Make an image containing 2D Gaussian sources.

    Parameters
    ----------
    shape : 2-tuple of int
        The shape of the output 2D image.

    source_table : `~astropy.table.Table`
        Table of parameters for the Gaussian sources.  Each row of the
        table corresponds to a Gaussian source whose parameters are
        defined by the column names.  With the exception of ``'flux'``,
        column names that do not match model parameters will be ignored
        (flux will be converted to amplitude).  If both ``'flux'`` and
        ``'amplitude'`` are present, then ``'flux'`` will be ignored.
        Model parameters not defined in the table will be set to the
        default value.

    Returns
    -------
    image : 2D `~numpy.ndarray`
        Image containing 2D Gaussian sources.

    See Also
    --------
    make_model_sources_image, make_random_gaussians_table

    Examples
    --------
    .. plot::
        :include-source:

        import matplotlib.pyplot as plt
        from astropy.table import QTable
        from photutils.datasets import (make_gaussian_prf_sources_image,
                                        make_noise_image)

        # make a table of Gaussian sources
        table = QTable()
        table['amplitude'] = [50, 70, 150, 210]
        table['x_0'] = [160, 25, 150, 90]
        table['y_0'] = [70, 40, 25, 60]
        table['sigma'] = [15.2, 5.1, 3., 8.1]

        # make an image of the sources without noise, with Gaussian
        # noise, and with Poisson noise
        shape = (100, 200)
        image1 = make_gaussian_prf_sources_image(shape, table)
        image2 = (image1 + make_noise_image(shape, distribution='gaussian',
                                            mean=5., stddev=5.))
        image3 = (image1 + make_noise_image(shape, distribution='poisson',
                                            mean=5.))

        # plot the images
        fig, (ax1, ax2, ax3) = plt.subplots(3, 1, figsize=(8, 12))
        ax1.imshow(image1, origin='lower', interpolation='nearest')
        ax1.set_title('Original image')
        ax2.imshow(image2, origin='lower', interpolation='nearest')
        ax2.set_title('Original image with added Gaussian noise'
                      r' ($\mu = 5, \sigma = 5$)')
        ax3.imshow(image3, origin='lower', interpolation='nearest')
        ax3.set_title(r'Original image with added Poisson noise ($\mu = 5$)')
    """
    model = IntegratedGaussianPRF(sigma=1)

    if 'sigma' in source_table.colnames:
        sigma = source_table['sigma']
    else:
        sigma = model.sigma.value  # default

    colnames = source_table.colnames
    if 'flux' not in colnames and 'amplitude' in colnames:
        source_table = source_table.copy()
        source_table['flux'] = (source_table['amplitude']
                                * (2.0 * np.pi * sigma * sigma))

    return make_model_sources_image(shape, model, source_table,
                                    oversample=1)


def make_4gaussians_image(noise=True):
    """
    Make an example image containing four 2D Gaussians plus a constant
    background.

    The background has a mean of 5.

    If ``noise`` is `True`, then Gaussian noise with a mean of 0 and a
    standard deviation of 5 is added to the output image.

    Parameters
    ----------
    noise : bool, optional
        Whether to include noise in the output image (default is
        `True`).

    Returns
    -------
    image : 2D `~numpy.ndarray`
        Image containing four 2D Gaussian sources.

    See Also
    --------
    make_100gaussians_image

    Examples
    --------
    .. plot::
        :include-source:

        import matplotlib.pyplot as plt
        from photutils.datasets import make_4gaussians_image

        image = make_4gaussians_image()
        plt.imshow(image, origin='lower', interpolation='nearest')
    """
    table = QTable()
    table['amplitude'] = [50, 70, 150, 210]
    table['x_mean'] = [160, 25, 150, 90]
    table['y_mean'] = [70, 40, 25, 60]
    table['x_stddev'] = [15.2, 5.1, 3.0, 8.1]
    table['y_stddev'] = [2.6, 2.5, 3.0, 4.7]
    table['theta'] = np.radians(np.array([145.0, 20.0, 0.0, 60.0]))

    shape = (100, 200)
    data = make_gaussian_sources_image(shape, table) + 5.0

    if noise:
        rng = np.random.RandomState(12345)
        data += rng.normal(loc=0.0, scale=5.0, size=shape)

    return data


def make_100gaussians_image(noise=True):
    """
    Make an example image containing 100 2D Gaussians plus a constant
    background.

    The background has a mean of 5.

    If ``noise`` is `True`, then Gaussian noise with a mean of 0 and a
    standard deviation of 2 is added to the output image.

    Parameters
    ----------
    noise : bool, optional
        Whether to include noise in the output image (default is
        `True`).

    Returns
    -------
    image : 2D `~numpy.ndarray`
        Image containing 100 2D Gaussian sources.

    See Also
    --------
    make_4gaussians_image

    Examples
    --------
    .. plot::
        :include-source:

        import matplotlib.pyplot as plt
        from photutils.datasets import make_100gaussians_image

        image = make_100gaussians_image()
        plt.imshow(image, origin='lower', interpolation='nearest')
    """
    n_sources = 100
    flux_range = [500, 1000]
    xmean_range = [0, 500]
    ymean_range = [0, 300]
    xstddev_range = [1, 5]
    ystddev_range = [1, 5]
    params = {'flux': flux_range,
              'x_mean': xmean_range,
              'y_mean': ymean_range,
              'x_stddev': xstddev_range,
              'y_stddev': ystddev_range,
              'theta': [0, 2 * np.pi]}

    rng = np.random.RandomState(12345)
    sources = QTable()
    for param_name, (lower, upper) in params.items():
        # Generate a column for every item in param_ranges, even if it
        # is not in the model (e.g., flux).  However, such columns will
        # be ignored when rendering the image.
        sources[param_name] = rng.uniform(lower, upper, n_sources)
    xstd = sources['x_stddev']
    ystd = sources['y_stddev']
    sources['amplitude'] = sources['flux'] / (2.0 * np.pi * xstd * ystd)

    shape = (300, 500)
    data = make_gaussian_sources_image(shape, sources) + 5.0

    if noise:
        rng = np.random.RandomState(12345)
        data += rng.normal(loc=0.0, scale=2.0, size=shape)

    return data


def make_wcs(shape, galactic=False):
    """
    Create a simple celestial `~astropy.wcs.WCS` object in either the
    ICRS or Galactic coordinate frame.

    Parameters
    ----------
    shape : 2-tuple of int
        The shape of the 2D array to be used with the output
        `~astropy.wcs.WCS` object.

    galactic : bool, optional
        If `True`, then the output WCS will be in the Galactic
        coordinate frame.  If `False` (default), then the output WCS
        will be in the ICRS coordinate frame.

    Returns
    -------
    wcs : `astropy.wcs.WCS` object
        The world coordinate system (WCS) transformation.

    See Also
    --------
    make_gwcs, make_imagehdu

    Notes
    -----
    The `make_gwcs` function returns an equivalent WCS transformation to
    this one, but as a `gwcs.wcs.WCS` object.

    Examples
    --------
    >>> from photutils.datasets import make_wcs
    >>> shape = (100, 100)
    >>> wcs = make_wcs(shape)
    >>> print(wcs.wcs.crpix)  # doctest: +FLOAT_CMP
    [50. 50.]
    >>> print(wcs.wcs.crval)  # doctest: +FLOAT_CMP
    [197.8925      -1.36555556]
    """
    wcs = WCS(naxis=2)
    rho = np.pi / 3.0
    scale = 0.1 / 3600.0  # 0.1 arcsec/pixel in deg/pix

    wcs.pixel_shape = shape
    wcs.wcs.crpix = [shape[1] / 2, shape[0] / 2]  # 1-indexed (x, y)
    wcs.wcs.crval = [197.8925, -1.36555556]
    wcs.wcs.cunit = ['deg', 'deg']
    wcs.wcs.cd = [[-scale * np.cos(rho), scale * np.sin(rho)],
                  [scale * np.sin(rho), scale * np.cos(rho)]]
    if not galactic:
        wcs.wcs.radesys = 'ICRS'
        wcs.wcs.ctype = ['RA---TAN', 'DEC--TAN']
    else:
        wcs.wcs.ctype = ['GLON-CAR', 'GLAT-CAR']

    return wcs


def make_gwcs(shape, galactic=False):
    """
    Create a simple celestial gWCS object in the ICRS coordinate frame.

    This function requires the `gwcs
    <https://github.com/spacetelescope/gwcs>`_ package.

    Parameters
    ----------
    shape : 2-tuple of int
        The shape of the 2D array to be used with the output
        `~gwcs.wcs.WCS` object.

    galactic : bool, optional
        If `True`, then the output WCS will be in the Galactic
        coordinate frame.  If `False` (default), then the output WCS
        will be in the ICRS coordinate frame.

    Returns
    -------
    wcs : `gwcs.wcs.WCS` object
        The generalized world coordinate system (WCS) transformation.

    See Also
    --------
    make_wcs, make_imagehdu

    Notes
    -----
    The `make_wcs` function returns an equivalent WCS transformation to
    this one, but as an `astropy.wcs.WCS` object.

    Examples
    --------
    >>> from photutils.datasets import make_gwcs
    >>> shape = (100, 100)
    >>> gwcs = make_gwcs(shape)
    >>> print(gwcs)
      From      Transform
    -------- ----------------
    detector linear_transform
        icrs             None
    """
    from gwcs import coordinate_frames as cf
    from gwcs import wcs as gwcs_wcs

    rho = np.pi / 3.0
    scale = 0.1 / 3600.0  # 0.1 arcsec/pixel in deg/pix

    shift_by_crpix = (models.Shift((-shape[1] / 2) + 1)
                      & models.Shift((-shape[0] / 2) + 1))

    cd_matrix = np.array([[-scale * np.cos(rho), scale * np.sin(rho)],
                          [scale * np.sin(rho), scale * np.cos(rho)]])

    rotation = models.AffineTransformation2D(cd_matrix, translation=[0, 0])
    rotation.inverse = models.AffineTransformation2D(
        np.linalg.inv(cd_matrix), translation=[0, 0])

    tan = models.Pix2Sky_TAN()
    celestial_rotation = models.RotateNative2Celestial(197.8925, -1.36555556,
                                                       180.0)

    det2sky = shift_by_crpix | rotation | tan | celestial_rotation
    det2sky.name = 'linear_transform'

    detector_frame = cf.Frame2D(name='detector', axes_names=('x', 'y'),
                                unit=(u.pix, u.pix))

    if galactic:
        sky_frame = cf.CelestialFrame(reference_frame=coord.Galactic(),
                                      name='galactic', unit=(u.deg, u.deg))
    else:
        sky_frame = cf.CelestialFrame(reference_frame=coord.ICRS(),
                                      name='icrs', unit=(u.deg, u.deg))

    pipeline = [(detector_frame, det2sky), (sky_frame, None)]

    return gwcs_wcs.WCS(pipeline)


def make_imagehdu(data, wcs=None):
    """
    Create a FITS `~astropy.io.fits.ImageHDU` containing the input 2D
    image.

    Parameters
    ----------
    data : 2D array_like
        The input 2D data.

    wcs : `None` or `~astropy.wcs.WCS`, optional
        The world coordinate system (WCS) transformation to include in
        the output FITS header.

    Returns
    -------
    image_hdu : `~astropy.io.fits.ImageHDU`
        The FITS `~astropy.io.fits.ImageHDU`.

    See Also
    --------
    make_wcs

    Examples
    --------
    >>> from photutils.datasets import make_imagehdu, make_wcs
    >>> shape = (100, 100)
    >>> data = np.ones(shape)
    >>> wcs = make_wcs(shape)
    >>> hdu = make_imagehdu(data, wcs=wcs)
    >>> print(hdu.data.shape)
    (100, 100)
    """
    data = np.asanyarray(data)
    if data.ndim != 2:
        raise ValueError('data must be a 2D array')

    if wcs is not None:
        header = wcs.to_header()
    else:
        header = None

    return fits.ImageHDU(data, header=header)


def _make_nonoverlap_coords(xrange, yrange, ncoords, min_separation, seed=0):
    from scipy.spatial import KDTree

    rng = np.random.default_rng(seed)

    xycoords = np.zeros((0, 2))
    niter = 1

    while xycoords.shape[0] < ncoords:
        if niter > 20:
            break

        x_new = rng.uniform(xrange[0], xrange[1], ncoords)
        y_new = rng.uniform(yrange[0], yrange[1], ncoords)
        new_xycoords = np.transpose((x_new, y_new))
        if niter == 1:
            xycoords = new_xycoords
        else:
            xycoords = np.vstack((xycoords, new_xycoords))

        dist, _ = KDTree(xycoords).query(xycoords, k=[2])
        mask = (dist >= min_separation).squeeze()
        xycoords = xycoords[mask]
        niter += 1

    xycoords = xycoords[0:ncoords]
    if len(xycoords) < ncoords:
        warnings.warn(f'Unable to produce {ncoords!r} coordinates.',
                      AstropyUserWarning)

    return xycoords


def make_test_psf_data(shape, psf_model, psf_shape, nsources,
                       flux_range=(100, 1000), min_separation=1, seed=0,
                       progress_bar=False):
    """
    Make an example image containing PSF model images.

    Source positions and fluxes are randomly generated using an optional
    ``seed``.

    Parameters
    ----------
    shape : 2-tuple of int
        The shape of the output image.

    psf_model : `astropy.modeling.Fittable2DModel`
        The PSF model.

    psf_shape : 2-tuple of int
        The shape around the center of the star that will used to
        evaluate the ``psf_model``.

    nsources : int
        The number of sources to generate.

    flux_range : tuple, optional
        The lower and upper bounds of the flux range.

    min_separation : float, optional
        The minimum separation between the centers of two sources. Note
        that if the minimum separation is too large, the number of
        sources generated may be less than ``nsources``.

    seed : int, optional
        A seed to initialize the `numpy.random.BitGenerator`. If `None`,
        then fresh, unpredictable entropy will be pulled from the OS.

    progress_bar : bool, optional
        Whether to display a progress bar when creating the sources. The
        progress bar requires that the `tqdm <https://tqdm.github.io/>`_
        optional dependency be installed. Note that the progress
        bar does not currently work in the Jupyter console due to
        limitations in ``tqdm``.

    Returns
    -------
    data : 2D `~numpy.ndarray`
        The simulated image.

    table : `~astropy.table.Table`
        A table containing the parameters of the generated sources.
    """
    hshape = (np.array(psf_shape) - 1) // 2
    xrange = (hshape[1], shape[1] - hshape[1])
    yrange = (hshape[0], shape[0] - hshape[0])

    xycoords = _make_nonoverlap_coords(xrange, yrange, nsources,
                                       min_separation=min_separation,
                                       seed=seed)
    x, y = np.transpose(xycoords)

    rng = np.random.default_rng(seed)
    flux = rng.uniform(flux_range[0], flux_range[1], nsources)
    flux = flux[:len(x)]

    sources = QTable()
    sources['x_0'] = x
    sources['y_0'] = y
    sources['flux'] = flux

    data = np.zeros(shape, dtype=float)

    sources_iter = sources
    if progress_bar:  # pragma: no cover
        desc = 'Adding sources'
        sources_iter = add_progress_bar(sources, desc=desc)

    for source in sources_iter:
        for param in ('x_0', 'y_0', 'flux'):
            setattr(psf_model, param, source[param])
        xcen = source['x_0']
        ycen = source['y_0']
        slc_lg, _ = overlap_slices(shape, psf_shape, (ycen, xcen), mode='trim')
        yy, xx = np.mgrid[slc_lg]
        data[slc_lg] += psf_model(xx, yy)

    sources.rename_column('x_0', 'x')
    sources.rename_column('y_0', 'y')
    sources.rename_column('flux', 'flux')

    return data, sources
