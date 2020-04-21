# -*- coding: utf-8 -*-
import warnings
from inspect import stack

import numpy as np


def bobyqa(fun, x0, args=(), bounds=None, options=None):
    """BOBYQA: Bounded Optimization BY Quadratic Approximation

    The algorithm is described in [M. J. D. Powell, The BOBYQA algorithm for bound constrained optimization without
    derivatives, Technical Report DAMTP 2009/NA06, Department of Applied Mathematics and Theoretical Physics, Cambridge
    University, Cambridge, UK, 2009].

    Parameters
    ----------
    fun: callable
        The objective function, which accepts a vector `x` at input and returns a scalar.
    x0: ndarray, shape (n,)
        The initial guess. The size of `x0` should be consistent with the objective function.
    args: tuple, optional
        The extra-arguments to pass to the objective function. For example,

            ``bobyqa(fun, x0, args, ...)``

        is equivalent to

            ``bobyqa(lambda x: fun(x, args), x0, ...)``

    bounds: either ndarray of tuple with shape(n,2), or Bounds, optional
        Bound constraints of the problem. The bounds can be specified in two different ways:
            1. Instance of `Bounds` class.
            2. Sequence of (lb, ub) pairs for each element in `x`. To specify that `x[i]` is unbounded below, set
               `bounds[i, 0]` to -np.inf; set `bounds[i, 1]` to np.inf if `x[i]` is unbounded above.
    options: dict, optional
        The options passed to the solver. It is a structure that contains optionally:
            rhobeg: float, optional
                Initial value of the trust region radius, which should be a positive scalar. `options['rhobeg']` should
                be typically set roughly to one tenth of the greatest expected change to a variable. By default, it is
                1.
            rhoend: float, optional
                Final value of the trust region radius, which should be a positive scalar. `options['rhoend']` should
                indicate typically the accuracy required in the final values of the variables. Moreover,
                `options['rhoend']` should be no more than `options['rhobeg']` and is by default 1e-6.
            maxfev: int, optional
                Upper bound of the number of calls of the objective function `fun`. Its value must be not less than
                `options['npt']`+1. By default, it is 500*n.
            npt: int, optional
                Number of interpolation points of each model used in Powell's Fortran code. By default, it is 2*n+1.
            ftarget: float, optional
                Target value of the objective function. If a feasible iterate achieves an objective function value lower
                or equal to `options['ftarget']`, the algorithm stops immediately. By default, it is -np.inf.
            scale: bool, optional
                Flag indicating whether to scale the problem. If it is True, the variables will be scaled according to
                the bounds constraints if any. By default, it is False.
            quiet: bool, optional
                Flag of quietness of the interface. If it is set to True, the output message will not be printed. This
                flag does not interfere with the warning and error printing.
            classical: bool, optional
                Flag indicating whether to call the classical Powell code or not. By default, it is False.
            debug: bool, optional
                Debugging flag. By default, it is False.
            chkfunval: bool, optional
                Flag used when debugging. If both `options['debug']` and `options['chkfunval']` are True, an extra
                function evaluation would be performed to check whether the returned objective function value is
                consistent with the returned x. By default, it is False.

    Returns
    -------
    res: OptimizeResult
        The results of the solver. Check ``pdfo.OptimizeResult`` for a description of the attributes.

    Notes
    -----
    The signature of this function is consistent with the `minimize` function available in ``scipy.optimize``, included
    in the SciPy package.

    See https://www.pdfo.co for more information.

    See also
    --------
    cobyla : Constrained Optimization BY Linear Approximations
    lincoa : LINearly Constrained Optimization Algorithm
    newuoa : NEW Unconstrained Optimization Algorithm
    uobyqa : Unconstrained Optimization BY Quadratic Approximation
    pdfo : Powell's Derivative-Free Optimization solvers

    Examples
    --------
    1. The following code

    >>> from pdfo import *
    >>> import numpy as np
    >>> bounds = Bounds(0, 1)
    >>> options = {'maxfev': 50}
    >>> bobyqa(np.cos, 0, bounds=bounds, options=options)

    solves
        min  cos(x)
        s.t. 0 <= x <= 1
    starting from x0 = 0 with at most 50 function evaluations.

    2. The following code

    >>> from pdfo import *
    >>> obj = lambda x: x[0]**2 + x[1]**2
    >>> bounds = Bounds([0, 0.5], [2, 3])
    >>> options = {'maxfev': 200}
    >>> bobyqa(obj, [0, 1], bounds=bounds, options=options)

    solves
        min  x^2 + y^2
        s.t. 0 <= x <= 2
             0.5 <= y <= 3
    starting from [x0, y0] = [0, 1] with at most 200 function evaluations.

    Authors
    -------
    Tom M. RAGONNEAU (tom.ragonneau@connect.polyu.hk)
    and Zaikun ZHANG (zaikun.zhang@polyu.edu.hk)
    Department of Applied Mathematics,
    The Hong Kong Polytechnic University.

    Dedicated to late Professor M. J. D. Powell FRS (1936--2015).
    """
    try:
        from .gethuge import gethuge
    except ImportError:
        from ._dependencies import import_error_so
        import_error_so('gethuge')

    from ._dependencies import prepdfo, postpdfo

    fun_name = stack()[0][3]  # name of the current function
    if len(stack()) >= 3:
        invoker = stack()[1][3].lower()
    else:
        invoker = ''

    # a cell that records all the warnings
    # Why do we record the warning message in output['warnings'] instead of prob_info['warnings']? Because, if bobyqa is
    # called by pdfo, then prob_info will not be passed to postpdfo, and hence the warning message will be lost. To the
    # contrary, output will be passed to postpdfo anyway.
    output = dict()
    output['warnings'] = []

    # preprocess the inputs
    fun_c, x0_c, bounds_c, _, options_c, _, prob_info = prepdfo(fun, x0, args, bounds=bounds, options=options)

    if prob_info['infeasible']:
        # the problem turned out infeasible during prepdfo
        exitflag = -4
        nf = 0
        x = np.full(x0_c.size, np.nan)
        fx = np.nan
        fhist = np.array([], dtype=np.float64)
        constrviolation = np.nan
        chist = np.array([], dtype=np.float64)
    elif prob_info['nofreex']:
        # x was fixed by the bound constraints during prepdfo
        exitflag = 13
        nf = 1
        x = prob_info['fixedx_value']
        fx = fun_c(x)
        fhist = np.array([fx], dtype=np.float64)
        constrviolation = prob_info['constrv_fixedx']
        chist = np.array([constrviolation], dtype=np.float64)
    else:
        # the problem turns out 'normal' during prepdfo extract the options and parameters
        npt = options_c['npt']
        maxfev = options_c['maxfev']
        rhobeg = options_c['rhobeg']
        rhoend = options_c['rhoend']
        ftarget = options_c['ftarget']

        # the largest integer in the fortran functions; the factor 0.99 provides a buffer
        max_int = np.floor(0.99 * gethuge('integer'))
        n = x0_c.size

        # the smallest nw, i.e., the nw with npt = n + 2
        min_nw = (n + 7) * (2 * n + 2) + 3 * n * (n + 5) / 2
        if min_nw + 1 >= max_int:
            executor = invoker.lower() if invoker == 'pdfo' else fun_name
            # nw would suffer from overflow in the Fortran code, exit immediately
            raise SystemError('{}: problem too large for {}. Try other solvers.'.format(executor, fun_name))

        # the largest possible value for npt given that nw <= max_int
        max_npt = \
            max(n + 2, np.floor(0.5 * (-(n + 5) + np.sqrt((n - 5) ** 2 + 4 * (max_int - 3 * n * (n + 5) / 2 - 1)))))
        if npt > max_npt:
            npt = max_npt
            w_message = \
                '{}: npt is so large that it is unable to allocate the workspace; it is set to {}'.format(fun_name, npt)
            warnings.warn(w_message, Warning)
            output['warnings'].append(w_message)
        if maxfev > max_int:
            maxfev = max_int
            w_message = \
                '{}: maxfev exceeds the upper limit of Fortran integer; it is set to {}'.format(fun_name, maxfev)
            warnings.warn(w_message, Warning)
            output['warnings'].append(w_message)

        # call the Fortran code
        try:
            if options_c['classical']:
                from . import fbobyqa_classical as fbobyqa
            else:
                from . import fbobyqa
        except ImportError:
            from ._dependencies import import_error_so
            import_error_so()

        x, fx, exitflag, fhist, chist, constrviolation = \
            fbobyqa.mbobyqa(npt, x0_c, bounds_c['lb'], bounds_c['ub'], rhobeg, rhoend, 0, maxfev, ftarget, fun_c)
        nf = int(fbobyqa.fbobyqa.nf)

    # postprocess the result
    return postpdfo(x, fx, exitflag, output, fun_name, nf, fhist, options_c, prob_info, constrviolation, chist)