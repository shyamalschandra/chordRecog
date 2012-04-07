import numpy as np
import activation as act
import error
from utilities import unsqueeze
from itertools import izip
from scipy.optimize import fmin_bfgs, fmin_l_bfgs_b

class NeuralNet():
    '''
    Creates a model of a feedforward neural network
    '''
    
    def __init__(self, neuronStruct, **args):
        '''
        Creates a model of a feedforward neural network.
        Assumes complete connectivity between each layer's nodes.
        
        PARAMETERS
        ----------
        neuronStruct {1 x N+1}: number of neurons in each of N+1 layers (including input)
        args:
            actFunc {1 x N}: list of activation functions to use in each of N layers (discluding input)
        '''

        # number of layers (including hidden and output layers but discluding input layer)
        self.N = len(neuronStruct)-1

        # number of inputs
        self.D = neuronStruct[0]
        # number of outputs
        self.K = neuronStruct[-1]

        # prepare activation functions
        if "actFunc" in args:
            if len(args["actFunc"]) != self.N:
                raise ValueError("NeuralNet: invalid number of activation functions")
            actFunc = args["actFunc"]
        else:
            actFunc = [act.Sigmoid()] * self.N

        # instantiate layers
        self.layers = []
        for i in range(1,self.N+1):
            self.layers.append(Layer(neuronStruct[i-1], neuronStruct[i], actFunc[i-1]))

    def calcOutput(self, input):
        '''
        Run all data points through the neural network

        PARAMETERS
        ----------
        input {TxD}: input data, T points of dimensionality D
        
        RETURNS
        -------
        output {TxK}: output of the network, T points of dimensionality K (number of network outputs)
        '''

        input = unsqueeze(input,2)
        T,D = input.shape

        if D != self.D:
            raise ValueError("NeuralNet: invalid input dimensions")

        # run the input through the network to attain output
        output = np.zeros([T, self.K])

        # for each input point
        for t, i in enumerate(input):
            signal = i
            for l in self.layers:
                signal = l.calcOutput(signal)
            output[t,:] = signal

        return output

    def flattenWeights(self):
        '''
        Helper function: flattens weight matrices for each layer to a row vector.
        '''
        w = np.empty(self._numWeights())
        wInd = 0
        for l in self.layers:
            w[wInd:wInd+l.w.size] = l.w.flatten()
            wInd += l.w.size

        return w

    def flattenWeightsRef(self):
        '''
        Helper function: flattens weight matrices for each layer to a row vector.
        IMPORTANT: each element of the flattened vector is a reference to a weight in the neural network
                   *** This means changing an element in the returned array changes the network weights ***
        This is useful in iterative optimization to avoid excessive for loops at each step
        '''
        w = np.empty(self._numWeights())
        wInd = 0
        for l in self.layers:
            w[wInd:wInd+l.w.size] = l.w.flatten()
            l.w = w[wInd:wInd+l.w.size]
            l.w.shape = (l.M, l.D+1)
            wInd += l.w.size

        return w

    def setWeights(self, w):
        '''
        Helper function: sets the network layer weights from a flattened row vector.
        '''
        if w.size != self._numWeights():
            raise ValueError("NeuralNet: invalid parameter vector size, can not set parameters")

        wInd = 0
        for l in self.layers:
            l.w = w[wInd:wInd+l.w.size].reshape(l.w.shape)
            wInd += l.w.size

    def _numWeights(self):
        '''
        Helper function: calculates the number of weights in all of the neural network layers.
        '''
        numW = 0
        for l in self.layers:
            numW += l.w.size
        return numW   

class Layer():
    '''
    Creates a single perceptron layer of a feedforward neural network
    '''

    def __init__(self, D, M, actFunc):
        '''
        Creates a layer object

        PARAMETERS
        ----------
        D: number of input neurons (neurons in the previous layer)
        M: number of neurons in the layer
        actFunc {Activation}: activation function for the layer
        '''
        self.D = D
        self.M = M

        # randomize weights within the range of the activation function
        #min = actFunc.outputMinMax[0] / (2.0 * M)
        #max = actFunc.outputMinMax[1] / (2.0 * M)
        min = -1.0
        max = 1.0
        # absorb bias parameters into the weight parameters by defining an 
        # additional input variable Xo = 1
        self.w = np.random.uniform(min, max, [M,D+1])

        # vector of input prepended with 1 to handle bias
        self.input = np.zeros(D+1)
        self.input[0] = 1.0

        # output before activation
        self.a = np.zeros(M)

        # set activation function for layer
        self.actFunc = actFunc

        # if softmax activation, check partition bounds
        if isinstance(self.actFunc, act.SoftMax) and self.actFunc._partition is not None:
            for part in self.actFunc._partition:
                if part <= 0 or part >= self.M:
                    raise ValueError("NeuralNet: invalid partition for softmax activation function output")

    def calcOutput(self, input):
        self.input[1:] = input
        self.a = np.sum(self.w * self.input, axis=1)
        return self.actFunc(self.a)

class Trainer():
    '''
    Trainer for the neural network.
    '''

    def __init__(self, net, errorFunc, show, Xtrain = None, Ytrain = None):
        self._net = net
        self.train = Xtrain
        self.target = Ytrain
        self._show = show
        self._err = 0.0
        self._iter = 0

        # for gradient descent algorithms
        self._eta = None

        # set error function
        if errorFunc == 'SSE':
            self._errorFunc = error.SSE()
        elif errorFunc == 'KLDiv':
            self._errorFunc = error.KLDiv()
        else:
            raise NotImplementedError("This error function has not been implemented yet")

        # keep track of error for plotting
        self.errHistory = []

        # roll out all network weights as initial guess for optimization function
        # **careful** change this vector -> change network weights
        self._w = self._net.flattenWeightsRef()

    def setData(self, Xtrain, Ytrain):
        self.train = unsqueeze(Xtrain,2)
        self.target = unsqueeze(Ytrain,2)

    def clearMemory(self):
        del self.errHistory[:]

    def _objFunc(self, w):
        '''
        The objective function.

        PARAMETERS
        ----------
        w: flattened vector of network weights at a given iteration

        RETURNS
        -------
        err {float}: error according to the error function of all outputs versus targets 
        '''
        # update neural network weights
        self._w[:] = w

        # first run the input data through the neural net
        output = self._net.calcOutput(self.train)

        # now calculate error
        self._err = self._errorFunc(output, self.target)
        
        return self._err

    def _jacObjFunc(self, w, trainInd = None):
        '''
        Calculates the jacobian of the objective function using backpropagation

        PARAMETERS
        ----------
        w: flattened vector of network weights at a given iteration

        RETURNS
        -------
        delta: vector with length equal to the number of weights in the network. 
               Each element is d(E)/d(w_ji) = d(E)/d(a_j) * d(a_j)/d(w_ji)
        '''
        # update network weights
        self._w[:] = w

        jacob = np.zeros(w.size)

        # shouldn't slow down batch training, since it will just copy a reference in this case
        train = self.train if trainInd is None else self.train[[trainInd],:]
        target = self.target if trainInd is None else self.target[[trainInd],:]

        # sum gradients over all input points
        for inPoint, targPoint in izip(train, target):
            # run the input data through the neural net
            # outPoint {1xK}
            outPoint = self._net.calcOutput(inPoint[np.newaxis,:])

            jInd = w.size
            # calculate delta at the output neurons
            lLayer = self._net.layers[-1]
            delta = self._errorFunc.derivative(outPoint, targPoint) * lLayer.actFunc.derivative(outPoint)
            delta = delta.T
            for lInd in reversed(range(self._net.N)):
                l = self._net.layers[lInd]
                numW = l.w.size

                # calculate partial error gradients for weights feeding into this layer
                # here input refers to the output of the previous layer (including activation)
                jacob[jInd-numW:jInd] += np.dot(delta, l.input[np.newaxis,:]).flatten()

                # calculate deltas for previous layer
                # (do not include delta for bias, since that isn't backed up)
                if lInd > 0:
                    lPrev = self._net.layers[lInd-1]
                    delta = np.dot(l.w.T[1:,:], delta) * lPrev.actFunc.derivative(l.input[1:,np.newaxis])

                jInd -= numW

        return jacob
                
    def _optCallback(self, w, log = True):
        '''
        Called after each iteration of optimization, as _optCallback(w), where w is the current parameter vector.

        PARAMETERS
        ----------
        w: flattened vector of network weights at a given iteration
        '''
        if self._iter % self._show == 0:
            print "Iteration ", self._iter, "; error: ", self._err / len(self.train)
    
        if log:
            self.errHistory.append(self._err / len(self.train))

        self._iter += 1
        
    def trainGradDesc(self, eta = 1e-2, convEps = 1e-5, maxiter = 25, sequential = True):
        '''
        GRADIENT DESCENT
        ----------------
        eta {float}: learning rate
            Default: 1e-2
        sequential {Boolean}: use sequential or batch training
            Default: sequential
        maxiter {Int}: maximum number of training iterations
            Default: 1000
        convEps {Float}: convergence criterion (when to stop iterating)
        '''
        T = len(self.train)

        if sequential:
            prevErr = np.inf
            # for each training iteration
            for tind in xrange(maxiter):
                # train one-by-one
                for i in xrange(T):
                    # calculate weight gradients and update
                    self._w[:] -= eta * self._jacObjFunc(self._w, i)

                # calculate error over all training points
                self._objFunc(self._w)
                self._optCallback(None, log = True)

                # check termination conditions satisfied
                if abs(prevErr - self._err) < convEps:
                    break

                prevErr = self._err

        return self.errHistory

    '''
    check error and modify eta after each observation
    def trainAdaptGradDesc(self, etaInit = 1e-2, etaInc = 1.1, etaDec = 0.5, convEps = 1e-5, maxiter = 25, sequential = True):
        T = len(self.train)
        eta = etaInit

        if sequential:
            prevErr = np.inf
            wCache = self._w.copy()

            # for each training iteration
            for tind in xrange(maxiter):
                # train one-by-one
                for i in xrange(T):
                    #print "obs: ", i
                    errDec = False
                    while not errDec:
                        # calculate weight gradients and update
                        self._w[:] -= eta * self._jacObjFunc(self._w, trainInd = i)

                        # calculate error over all training points
                        if self._objFunc(self._w) < prevErr:
                            # all good, increase the learning rate
                            eta *= etaInc
                            wCache = self._w.copy()
                            errDec = True
                            prevErr = self._err
                            #print "+eta: ", eta
                        else:
                            # rollback and start again with decreased learning rate
                            self._w[:] = wCache
                            eta *= etaDec
                            #print "-eta: ", eta

                            if eta < 1e-6:
                                print "eta hit lower bound, resetting ..."
                                eta = 1e-3
                                break

                self._optCallback(None, log = True)

                # check termination conditions satisfied
                if abs(prevErr - self._err) < convEps:
                    break

        return self.errHistory
    '''
    
    def trainAdaptGradDesc(self, etaInit = 1e-2, etaInc = 1.1, etaDec = 0.5, convEps = 1e-5, maxiter = 25, sequential = True):
        '''
        ADAPTIVE GRADIENT DESCENT
        -------------------------
        eta {float}: learning rate
            Default: 1e-2
        etaInc {float}: ratio to increase learning rate (> 1)
            Default: 1.1
        etaDec {float}: ratio to decrease learning rate (< 1)
            Default: 0.5
        sequential {Boolean}: use sequential or batch training
            Default: sequential
        maxiter {Int}: maximum number of training iterations
            Default: 1000
        convEps {Float}: convergence criterion (when to stop iterating)

        Check error and modify eta after each batch of training data.
        '''
        T = len(self.train)
        
        if self._eta is None:
            self._eta = etaInit

        if sequential:
            wCache = self._w.copy()
            prevIterErr = np.inf

            # for each training iteration
            for tind in xrange(maxiter):
                errDec = False
                while not errDec:
                    # train one-by-one
                    for i in xrange(T):
                        # calculate weight gradients and update
                        self._w[:] -= self._eta * self._jacObjFunc(self._w, trainInd = i)

                    # calculate error over all training points
                    prevErr = self.errHistory[-1] if len(self.errHistory) > 0 else np.inf
                    if self._err / len(self.train) < prevErr:
                        # all good, increase the learning rate
                        self._eta *= etaInc
                        errDec = True
                        print "+eta: ", self._eta
                    else:
                        # rollback and start again with decreased learning rate
                        self._w[:] = wCache
                        self._eta *= etaDec
                        print "-eta: ", self._eta

                        if self._eta < 1e-6:
                            print "eta hit lower bound, resetting ..."
                            self._eta = etaInit
                            break

                self._optCallback(None, log = True)

                # check termination conditions satisfied
                if abs(prevIterErr - self._err) < convEps:
                    break

                prevIterErr = self._err

        return self.errHistory
                
    def trainBFGS(self, **optArgs):
        '''
        BFGS
        ----
        maxiter {Int}: maximum number of training iterations
        gtol {Float}: gradient the norm must be less than before succesful termination
        '''
        wstar = fmin_bfgs(self._objFunc, self._w.copy(), fprime = self._jacObjFunc, callback = self._optCallback, **optArgs)        
        
        # set the optimal weights
        self._w[:] = wstar

        return self.errHistory

    def trainL_BFGS_B(self, **optArgs):
        '''
        L-BFGS-B
        --------
        bounds (Int,Int): bounds on each weight parameter as tuple (min,max), default: None
        m {Int}: number of terms to approximate the hessian
            Default: 10
        factr {Float}: scalar to control number of iterations.
            Low accuracy: 1e12
            Moderate accuracy: 1e7
            High accuracy: 10.0
            Default: 1e7
        pgtol {Float}: iteration stops when max(grad) <= pgtol
            Default: 1e-05
        iprint {Int}: frequency of output
            silent: -1
            print to stdout: 0
            print to file named iterate.dat in pwd: 1
            Default: -1
        maxfun {Int}: maximum number of function evaluations
            Default: 15000
        '''

        optArgs["bounds"] = [optArgs["bounds"]] * len(self._w)
        wstar, finalErr, d = fmin_l_bfgs_b(self._objFunc, self._w.copy(), fprime=self._jacObjFunc, **optArgs)

        if d["warnflag"] == 0:
            print "Converged to a solution in ", d["funcalls"], " steps."
        elif d["warnflag"] == 1:
            print "Exceeded maximum number of iterations."
        else:
            print d["task"]

        self.errHistory.append(finalErr)

        # set the optimal weights
        self._w[:] = wstar

        return self.errHistory

