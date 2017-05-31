# Spark-Tensorflow integration and hyperparameter tuning demo with MNIST handwritten digit recognition.
# Sanket Shahane

import pyspark

import numpy
import itertools
from keras import optimizers
from keras.datasets import mnist
from keras.models import Sequential
from keras.layers import Dense
from keras.layers import Dropout
from keras.utils import np_utils

# get the spark context
sc = pyspark.SparkContext()
# few steps to get the training data.
seed = 7
numpy.random.seed(seed)
(X_train, y_train), (X_test, y_test) = mnist.load_data()
# flatten 28*28 images to a 784 vector for each image
num_pixels = X_train.shape[1] * X_train.shape[2]
X_train = X_train.reshape(X_train.shape[0], num_pixels).astype('float32')
X_test = X_test.reshape(X_test.shape[0], num_pixels).astype('float32')
# normalize inputs from 0-255 to 0-1
X_train = X_train / 255
X_test = X_test / 255
# one hot encode outputs
y_train = np_utils.to_categorical(y_train)
y_test = np_utils.to_categorical(y_test)
num_classes = y_test.shape[1]

X_train = sc.broadcast(X_train)
y_train = sc.broadcast(y_train)

# define baseline model
def compile_and_execute_model(learning_rate = 0.01, layer1_neurons = 784, optimizer = 'adam', loss = 'categorical_crossentropy'):
	# Design and create model
	model = Sequential()
	model.add(Dense(layer1_neurons, input_dim=num_pixels, kernel_initializer='normal', activation='relu'))
	model.add(Dense(num_classes, kernel_initializer='normal', activation='softmax'))
	adam_optimizer = optimizers.Adam(lr = learning_rate, decay = 0.005)
	# Compile the model
	model.compile(loss=loss, optimizer=adam_optimizer, metrics=['accuracy'])
	# Train the model
	model.fit(X_train.value, y_train.value, validation_data=(X_test, y_test), epochs=10, batch_size=200, verbose=2)
	# Final evaluation of the model
	scores = model.evaluate(X_test, y_test, verbose=0)
	print("Error: %.2f%%" % (100-scores[1]*100))
	print model.get_config()
	parameters = {'configuration':model.get_config(), 'weights':model.get_weights(), 'optimizer': 'adam', 'loss':loss, 'error':scores[0]}
	#return (model.get_config(),model.get_weights(),adam,loss)
	return (parameters)

# reconstruct the model from the results
def reconstruct_best_model(results):
	min_error = results[0]['error']
	min_index = 0
	for i,m in enumerate(results):
		if m['error'] < min_error:
			min_error = m['error']
			min_index = i
	# set this to the index of the actual best model based on minimum loss
	best_model = results[min_index]
	model_reconstruction = Sequential.from_config(best_model['configuration'])
	model_reconstruction.set_weights(best_model['weights'])
	# Following step does not train the model again. Just compiles so it can predict in future
	model_reconstruction.compile(optimizer=best_model['optimizer'], loss=best_model['loss'])
	scores = model_reconstruction.evaluate(X_test, y_test, verbose=0)
	print 'best score:',scores
	return model_reconstruction

# pass the learning rate and layer1_neurons to experiment out with
def hypermarameter_tuning(learning_rate = [0.01,0.005,0.025], layer1_neurons = [784,500]):
	# all combinations of parameters
	all_experiments = list(itertools.product(learning_rate, layer1_neurons)) 
	print(len(all_experiments))
	num_nodes = 1
	n = max(2, int(len(all_experiments) // num_nodes))
	n = 1
	# making groups of the parameters to run in parallel on all the nodes
	grouped_experiments = [all_experiments[i:i+n] for i in range(0, len(all_experiments), n)]
	all_exps_rdd = sc.parallelize(grouped_experiments, numSlices=len(grouped_experiments))
	# train in parallel and return the results
	results = all_exps_rdd.flatMap(lambda z: [compile_and_execute_model(*y) for y in z]).collect()
	return results

if __name__ == '__main__':
	results = hypermarameter_tuning([0.01,0.03],[700,400])
	print 'Results are ready!'
	bestModel = reconstruct_best_model(results)
	print 'best model available'
# use best_model to predict, evaluate, or save to disk. Requires import h5
# bestModel.save('/path/to/savefile.h5')


# Notes:
# if pyspark is not found on your machine, extract the pyspark and py4j located in the spark-dist/python/lib directory
# export PYTHONPATH="$PYTHONPATH:/$FUSION_HOME/apps/spark-dist/python/lib
# e.g. for me it is
# export PYTHONPATH="$PYTHONPATH:/Users/sanket/home/fusion3.1/3.1.0-beta1/apps/spark-dist/python/lib"
# export SPARK_HOME="/Users/sanket/home/fusion3.1/3.1.0-beta1/apps/spark-dist/"

# works fine with broadcasted variables. Note: The input has to be numpy array and loaded at once in the memory to be broadcasted.
# example to broadcast:
# x = rdd.map(lambda x: tuple(np.array(x)))
# x = sc.broadcast(x)
# x.value