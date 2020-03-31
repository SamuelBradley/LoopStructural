import logging

import numpy as np
from scipy.sparse import coo_matrix, bmat, eye
from scipy.sparse import linalg as sla

from LoopStructural.interpolators.geological_interpolator import \
    GeologicalInterpolator

logger = logging.getLogger(__name__)


class DiscreteInterpolator(GeologicalInterpolator):

    def __init__(self, support):
        """
        Base class for a discrete interpolator e.g. piecewise linear or finite difference which is
        any interpolator that solves the system using least squares approximation

        Parameters
        ----------
        support
            A discrete mesh with, nodes, elements, etc
        """
        GeologicalInterpolator.__init__(self)
        self.B = []
        self.support = support
        self.region_function = None
        self.region = np.arange(0, support.n_nodes)
        self.region_map = np.zeros(support.n_nodes).astype(int)
        # self.region_map[self.region] = np.array(range(0,
        # len(self.region_map[self.region])))
        self.nx = len(self.support.nodes[self.region])
        if self.shape == 'square':
            self.B = np.zeros(self.nx)
        self.c_ = 0
        self.A = []  # sparse matrix storage coo format
        self.col = []
        self.row = []  # sparse matrix storage
        self.solver = None
        self.eq_const_C = []
        self.eq_const_row = []
        self.eq_const_col = []
        self.eq_const_d = []
        self.eq_const_c_ = 0

    def set_property_name(self, propertyname):
        """
        Set the property name attribute, this is usually used to
        save the property on the support

        Parameters
        ----------
        propertyname

        Returns
        -------

        """
        self.propertyname = propertyname

    def set_region(self, region=None):
        """
        Set the region of the support the interpolator is working on

        Parameters
        ----------
        region - function(position)
            return true when in region, false when out

        Returns
        -------

        """
        # evaluate the region function on the support to determine
        # which nodes are inside update region map and degrees of freedom
        self.region_function = region
        self.region = region(self.support.nodes)
        self.region_map = np.zeros(self.support.n_nodes).astype(int)
        self.region_map[self.region] = np.array(
            range(0, len(self.region_map[self.region])))
        self.nx = len(self.support.nodes[self.region])

    def set_interpolation_weights(self, weights):
        """
        Set the interpolation weights dictionary

        Parameters
        ----------
        weights - dictionary
            Entry of new weights to assign to self.interpolation_weights

        Returns
        -------

        """
        for key in weights:
            self.up_to_date = False
            self.interpolation_weights[key] = weights[key]

    def reset(self):
        """
        Reset the interpolation constraints

        """
        logger.debug("Resetting interpolation constraints")
        self.c_ = 0
        self.A = []  # sparse matrix storage coo format
        self.col = []
        self.row = []  # sparse matrix storage
        self.eq_const_C = []
        self.eq_const_row = []
        self.eq_const_col = []
        self.eq_const_d = []
        self.eq_const_c_ = 0
        self.B = []

    def add_constraints_to_least_squares(self, A, B, idc):
        """
        Adds constraints to the least squares system. Automatically works
        out the row
        index given the shape of the input arrays

        Parameters
        ----------
        A : numpy array / list
            RxC numpy array of constraints where C is number of columns,R rows
        B : numpy array /list
            B values array length R
        idc : numpy array/list
            RxC column index

        Returns
        -------

        """
        A = np.array(A)
        B = np.array(B)
        idc = np.array(idc)
        if np.any(np.isnan(idc)) or np.any(np.isnan(A)) or np.any(np.isnan(B)):
            logger.warning("Constraints contain nan not adding constraints")
            return
        nr = A.shape[0]
        if len(A.shape) > 2:
            nr = A.shape[0] * A.shape[1]
        rows = np.arange(0, nr).astype(int)
        rows = np.tile(rows, (A.shape[-1], 1)).T
        rows += self.c_
        self.c_ += nr
        if self.shape == 'rectangular':
            # don't add operator where it is = 0 to the sparse matrix!
            A = A.flatten()
            rows = rows.flatten()
            idc = idc.flatten()
            B = B.flatten()
            mask = A == 0
            self.A.extend(A[~mask].tolist())
            self.row.extend(rows[~mask].tolist())
            self.col.extend(idc[~mask].tolist())
            self.B.extend(B.tolist())

    def add_equality_constraints(self, node_idx, values):
        """
        Adds hard constraints to the least squares system. For now this just
        sets
        the node values to be fixed using a lagrangian.

        Parameters
        ----------
        node_idx : numpy array/list
            int array of node indexes
        values : numpy array/list
            array of node values

        Returns
        -------

        """
        # map from mesh node index to region node index
        gi = np.zeros(self.support.n_nodes)
        gi[:] = -1
        gi[self.region] = np.arange(0, self.nx)
        idc = gi[node_idx]
        outside = ~(idc == -1)

        self.eq_const_C.extend(np.ones(idc[outside].shape[0]).tolist())
        self.eq_const_col.extend(idc[outside].tolist())
        self.eq_const_row.extend((np.arange(0, idc[outside].shape[0])))
        self.eq_const_d.extend(values[outside].tolist())
        self.eq_const_c_ += idc[outside].shape[0]

    def build_matrix(self, square=True, damp=True):
        """
        Assemble constraints into interpolation matrix. Adds equaltiy
        constraints
        using lagrange modifiers if necessary

        Parameters
        ----------
        damp: bool
            Flag whether damping should be added to the diagonal of the matrix
        Returns
        -------
        Interpolation matrix and B
        """

        logger.info("Interpolation matrix is %i x %i"%(self.c_,self.nx))
        cols = np.array(self.col)
        A = coo_matrix((np.array(self.A), (np.array(self.row), \
                                           cols)), shape=(self.c_, self.nx),
                       dtype=float)  # .tocsr()
        B = np.array(self.B)
        if not square:
            logger.info("Using rectangular matrix, equality constraints are not used")
            return A, B
        AAT = A.T.dot(A)
        BT = A.T.dot(B)
        # add a small number to the matrix diagonal to smooth the results
        # can help speed up solving, but might also introduce some errors

        if self.eq_const_c_ > 0:
            logger.info("Equality block is %i x %i"%(self.eq_const_c_,self.nx))
            # solving constrained least squares using
            # | ATA CT | |c| = b
            # | C   0  | |y|   d
            # where A is the interpoaltion matrix
            # C is the equality constraint matrix
            # b is the interpolation constraints to be honoured
            # in a least squares sense
            # and d are the equality constraints
            # c are the node values and y are the
            # lagrange multipliers#
            C = coo_matrix(
                (np.array(self.eq_const_C), (np.array(self.eq_const_row),
                                             np.array(self.eq_const_col))),
                shape=(self.eq_const_c_, self.nx))
            d = np.array(self.eq_const_d)
            AAT = bmat([[AAT, C.T], [C, None]])
            BT = np.hstack([BT, d])
        if damp:
            logger.info("Adding eps to matrix diagonal")
            AAT += eye(AAT.shape[0]) * np.finfo('float').eps
        return AAT, BT

    def _solve_lu(self, A, B):
        """
        Call scipy LU decomoposition

        Parameters
        ----------
        A - square sparse matrix
        B : numpy vector

        Returns
        -------

        """
        lu = sla.splu(A.tocsc())
        sol = lu.solve(B)
        return sol[:self.nx]

    def _solve_lsqr(self, A, B, **kwargs):
        """
        Call scipy lsqr

        Parameters
        ----------
        A : rectangular sparse matrix
        B : vector

        Returns
        -------

        """

        lsqrargs = {}
        # lsqrargs['tol'] = 1e-12
        if 'iter_lim' in kwargs:
            logger.info("Using %i maximum iterations" % kwargs['iter_lim'])
            lsqrargs['iter_lim'] = kwargs['iter_lim']
        if 'damp' in kwargs:
            logger.info("Using damping coefficient")
            lsqrargs['damp'] = kwargs['damp']
        if 'atol' in kwargs:
            logger.info('Using a tolerance of %f' % kwargs['atol'])
            lsqrargs['atol'] = kwargs['atol']
        if 'btol' in kwargs:
            logger.info('Using btol of %f' % kwargs['btol'])
            lsqrargs['btol'] = kwargs['btol']
        if 'show' in kwargs:
            lsqrargs['show'] = kwargs['show']
        if 'conlim' in kwargs:
            lsqrargs['conlim'] = kwargs['conlim']
        return sla.lsqr(A,B, **lsqrargs)[0]

    def _solve_chol(self, A, B):
        """
        Call suitesparse cholmod through scikitsparse
        LINUX ONLY!

        Parameters
        ----------
        A - scipy.sparse.matrix
            square sparse matrix
        B - numpy array
            RHS of equation

        Returns
        -------

        """
        try:
            from sksparse.cholmod import cholesky
            factor = cholesky(A.tocsc())
            return factor(B)[:self.nx]
        except ImportError:
            logger.warning("Scikit Sparse not installed try using cg instead")
            return False

    def _solve_cg(self, A, B, precon=None, **kwargs):
        """
        Call scipy conjugate gradient

        Parameters
        ----------
        A : scipy.sparse.matrix
            square sparse matrix
        B : numpy vector
        precon : scipy.sparse.matrix
            a preconditioner for the conjugate gradient system
        kwargs
            kwargs to pass to scipy solve e.g. atol, btol, callback etc

        Returns
        -------
        numpy array
        """
        cgargs = {}
        cgargs['tol'] = 1e-12
        if 'maxiter' in kwargs:
            logger.info("Using %i maximum iterations"%kwargs['maxiter'])
            cgargs['maxiter'] = kwargs['maxiter']
        if 'x0' in kwargs:
            logger.info("Using starting guess")
            cgargs['x0'] = kwargs['x0']
        if 'tol' in kwargs:
            logger.info('Using tolerance of %f'%kwargs['tol'])
            cgargs['tol'] = kwargs['tol']
        if 'atol' in kwargs:
            logger.info('Using atol of %f'%kwargs['atol'])
            cgargs['atol'] = kwargs['atol']
        if 'callback' in kwargs:
            cgargs['callback'] = kwargs['callback']
        if precon is not None:
            cgargs['M'] = precon(A)
        return sla.cg(A, B, **cgargs)[0][:self.nx]

    def _solve_pyamg(self, A, B):
        """
        Solve least squares system using pyamg algorithmic multigrid solver

        Parameters
        ----------
        A :  scipy.sparse.matrix
        B : numpy array

        Returns
        -------

        """
        import pyamg
        return pyamg.solve(A, B, verb=False)[:self.nx]

    def _solve(self, solver='cg', **kwargs):
        """
        Main entry point to run the solver and update the node value
        attribute for the
        discreteinterpolator class

        Parameters
        ----------
        solver : string
            solver e.g. cg, lu, chol, custom
        kwargs
            kwargs for solver e.g. maxiter, preconditioner etc, damping for
        
        Returns
        -------
        bool
            True if the interpolation is run

        """
        self.c = np.zeros(self.support.n_nodes)
        self.c[:] = np.nan
        damp = True
        if 'damp' in kwargs:
            damp = kwargs['damp']
        if solver == 'lsqr':
            A, B =  self.build_matrix(False)
        else:
            A, B = self.build_matrix(damp=damp)

        # run the chosen solver
        if solver == 'cg':
            logger.info("Solving using conjugate gradient")
            self.c[self.region] = self._solve_cg(A, B, **kwargs)
        if solver == 'chol':
            self.c[self.region] = self._solve_chol(A, B)
        if solver == 'lu':
            logger.info("Solving using scipy LU")
            self.c[self.region] = self._solve_lu(A, B)
        if solver == 'pyamg':
            try:
                logger.info("Solving with pyamg solve")
                self.c[self.region] = self._solve_pyamg(A, B)
            except ImportError:
                logger.warn("Pyamg not installed using cg instead")
                self.c[self.region] = self._solve_cg(A, B)
        if solver == 'lsqr':
            self.c[self.region] = self._solve_lsqr(A, B, **kwargs)
        if solver == 'external':
            logger.warning("Using external solver")
            self.c[self.region] = kwargs['external'](A, B)[:self.nx]
        # check solution is not nan
        self.support.properties[self.propertyname] = self.c
        if np.all(self.c == np.nan):
            logger.warning("Solver not run, no scalar field")
        # if solution is all 0, probably didn't work
        if np.all(self.c[self.region] == 0):
            logger.warning("No solution, scalar field 0. Add more data.")

    def update(self):
        """
        Check if the solver is up to date, if not rerun interpolation using
        the previously used solver. If the interpolation has not been run
        before it will
        return False

        Returns
        -------
        bool

        """
        if self.solver is None:
            logging.debug("Cannot rerun interpolator")
            return False
        if not self.up_to_date:
            self.setup_interpolator()
            return self._solve(self.solver)

    def evaluate_value(self, evaluation_points):
        evaluation_points = np.array(evaluation_points)
        evaluated = np.zeros(evaluation_points.shape[0])
        mask = np.any(evaluation_points == np.nan, axis=1)

        if evaluation_points[~mask, :].shape[0] > 0:
            evaluated[~mask] = self.support.evaluate_value(
                evaluation_points[~mask], self.propertyname)
        return evaluated

    def evaluate_gradient(self, evaluation_points):
        """
        Evaluate the gradient of the scalar field at the evaluation points
        Parameters
        ----------
        evaluation_points

        Returns
        -------

        """
        if evaluation_points.shape[0] > 0:
            return self.support.evaluate_gradient(evaluation_points,
                                                  self.propertyname)
        return np.zeros((0, 3))