import sys
sys.path.insert(0, "..")

from learnHMMaligned import *
import ghmm
import pickle

'''
Chord recognition experiment
Using chordino chroma vector features aligned framewise with ground-truth annotations

PARAMETERS
----------
'''
M = 7               # number of gaussian components in the emission distribution mixture
covType = 'diag'    # covariance structure for emission distributions (diag or full)
quality = 'full'  # chord quality: full or simple
rotate = False      # rotate chromas and use quality as chord label
key = False         # include key information in chord labels
features = 'tb'     # features to use: t (treble) or b (bass) or both
norm = None         # feature norm
holdOut = (70,70)   # holdOut songnumber range (low,high) inclusive (not song ID's but in order of appearance in data files)
obsThresh = 2000    # chords with number of observations below obsThresh are discluded
addOne = True       # add one to pi and A before normalization
numTies = 11      # number of tied states (chord duration modeling)

# learn HMM model lambda = (pi, A, B) from ground truth
pi, A, B, labels, Xtest, Ytest, AIC = learnHMM(M=M, addOne=addOne, features=features, chordQuality=quality, rotateChroma=rotate, key=key, featureNorm=norm, covType=covType, holdOut=holdOut, obsThresh=obsThresh)

if numTies is not None:
    pi, A, B, labels = tieStates(pi, A, B, labels, D = 11)

# number of chords in ground truth
N = A.shape[0]

# fill the HMM with the learned parameters
hmm = ghmm.GHMM(N, labels = labels, pi = pi, A = A, B = B)

# pickle hmm model for future
rot = '1' if rotate else '0'
key = '1' if key else '0'
tie = str(numTies) if numTies is not None else 'NA'
fName = '../trainedhmms/exp1_M=' + str(M) + '_sig=' + covType + '_quality=' + quality + '_rotate=' + rot + '_key=' + key + '_tied=' + tie + '_holdOut=[' + str(holdOut[0]) + '_' + str(holdOut[1]) + ']'
outP = open(fName, 'w')
pickle.dump(hmm, outP)
outP.close()

accs = {}
# find optimal state sequence for each holdout test song
for sid in Xtest:
    pstar, qstar = hmm.viterbi(Xtest[sid])

    # report error
    numCorr = 0
    for qInd in range(len(Ytest[sid])):
        if numTies is not None:
            result = Ytest[sid][qInd].split("_")[0]
        else:
            result = Ytest[sid][qInd]

        if qstar[qInd] == result:
            numCorr += 1

    acc = float(numCorr) / len(Ytest[sid])
    accs[sid] = acc

acc = float(numCorr) / len(ytest)
print "recognition accuracy: ", acc
