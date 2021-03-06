
import numpy as np
import tensorflow as tf
import os
from tqdm import trange, tqdm
from skimage import io, transform
import argparse
import math
from scipy.stats import truncnorm
import matplotlib.pyplot as plt

DISC_LAYERS = 3
GEN_LAYERS = 2
SQ_IMG_SIZE = 32
BASE_PATH = os.path.dirname(os.path.realpath(__file__))

#arguments
def parse_arguments():
	parser = argparse.ArgumentParser(description='Description of your program')
	parser.add_argument('-d','--discriminator', help='Number of convolutional discriminator layers', required=False, default = '3')
	parser.add_argument('-g','--generator', help='Number of convolutional generator layers', required=False, default = '2')
	parser.add_argument('-s','--size', help='Size of square images in pixels, use 2^n', required=False, default = '32')
	parser.add_argument('-p','--path', help='Base path', required=False, default = os.path.realpath(__file__))
	args = vars(parser.parse_args())
	if int(args['size']) > 0:
		SQ_IMG_SIZE = int(args['size'])
	if int(args['discriminator']) > 0 and int(args['discriminator']) < math.log(SQ_IMG_SIZE,2):
		DISC_LAYERS = int(args['discriminator'])
	if 'generator' in args and int(args['generator']) > 0 and int(args['generator']):
		GEN_LAYERS = int(args['generator'])
	BASE_PATH = args['path']

parse_arguments()

Z_SIZE = 1000
BASE_GEN_SIZE = 8

def ensureDirectory(path):
	if not os.path.exists("{}/".format(path)):
		os.makedirs("{}/".format(path))

WRITER_PATH = BASE_PATH + "/writer"
ensureDirectory(WRITER_PATH)

MODEL_PATH = BASE_PATH + "/model"
ensureDirectory(MODEL_PATH)

OUTPUT_PATH = BASE_PATH + "/output"
ensureDirectory(OUTPUT_PATH)

DATA_PATH = BASE_PATH + "/training_data"
ensureDirectory(DATA_PATH)

def loadData(size):
	files_in = os.listdir('training_data')
	if size > len(files_in):
		size = len(files_in)
	files = np.random.choice(files_in, size=size)
	images = []
	for f in tqdm(files):
		images.append(transform.resize(io.imread('training_data/' + f), (SQ_IMG_SIZE,SQ_IMG_SIZE,3), mode='constant'))
	result = np.asarray(images)
	return result


def lrelu(x, alpha=0.1):
	return tf.nn.relu(x) - alpha * tf.nn.relu(-x)

def dcgan_generator(z, name = "g_generator"):
	with tf.variable_scope(name) as scope:
		if scope.trainable_variables():
			scope.reuse_variables()
		z = tf.reshape(z, [1, Z_SIZE], name="g_reshape0")
		reshape1 = tf.contrib.layers.fully_connected(z, SQ_IMG_SIZE*SQ_IMG_SIZE*4, activation_fn=None, biases_initializer=tf.contrib.layers.variance_scaling_initializer(), weights_initializer=tf.contrib.layers.variance_scaling_initializer())
		reshape2 = tf.reshape(reshape1, [1, 4, 4, SQ_IMG_SIZE*SQ_IMG_SIZE/4], name="g_reshape2")
		g_mid = generator_mid_layers(reshape2, GEN_LAYERS)
		g_final = tf.layers.conv2d_transpose(g_mid, 3, 3, strides = [2,2], padding = "SAME", use_bias=True, name = "g_conv_final", kernel_initializer = tf.contrib.layers.variance_scaling_initializer(), activation=tf.nn.sigmoid)
		print("g_final: {}".format(g_final.shape))
		return g_final

def generator_mid_layers(previous, LAYERS):
	for x in range(LAYERS):
		g = tf.layers.conv2d_transpose(previous, SQ_IMG_SIZE/(2**x), 3, strides = [2,2], padding = "SAME", use_bias=True, name = "g_conv{}".format(x), kernel_initializer = tf.contrib.layers.variance_scaling_initializer(), activation=tf.nn.relu)
		previous = g
		print("g{}: {}".format(x, g.shape))
	return g

def dcgan_discriminator(input_image, reuse=False, name = "d_discriminator"):
	with tf.variable_scope(name) as scope:
		if scope.trainable_variables():
			scope.reuse_variables()
		print("input_image: {}".format(input_image.shape))
		d_mid = discriminator_mid_layers(input_image, DISC_LAYERS, reuse)
		d_final = tf.layers.conv2d(d_mid, 2, 3, name="d_conv3", reuse=reuse, kernel_initializer = tf.contrib.layers.variance_scaling_initializer(), activation=None, padding="SAME")
		dr_final = lrelu(d_final)
		print("d_final: {}".format(dr_final.shape))
		dr_final = tf.reshape(dr_final,[1,SQ_IMG_SIZE*SQ_IMG_SIZE*2])
		scalar = tf.contrib.layers.fully_connected(dr_final, 1, reuse=reuse, activation_fn=None, biases_initializer=tf.contrib.layers.variance_scaling_initializer(), weights_initializer=tf.contrib.layers.variance_scaling_initializer(), scope=scope)
		return scalar

def discriminator_mid_layers(previous, LAYERS, reuse):
	for x in range(LAYERS):
		d = tf.layers.conv2d(previous, SQ_IMG_SIZE/(2**x), 3, name="d_conv{}".format(x), reuse=reuse, kernel_initializer = tf.contrib.layers.variance_scaling_initializer(), activation=None, padding="SAME")
		dr = lrelu(d)
		previous = dr
		print("d{}: {}".format(x, dr.shape))
	return dr

def get_z():
	return truncnorm(a=-1.0, b=1.0, scale=1.0).rvs(size=Z_SIZE)

EPOCHS = 1000
C = 0.0001
BETA_1 = 0.5
BETA_2 = 0.999
IMAGE_DIMS = [1,SQ_IMG_SIZE,SQ_IMG_SIZE,3]
N_CRITIC = 5
LAMBDA = 10
DATA_SIZE = 10
N_SAMPLES = 10
training_images = loadData(DATA_SIZE)
print("Loaded {} training images!".format(len(training_images)))

true_img = tf.placeholder(tf.float32, IMAGE_DIMS)
z_node = tf.placeholder(tf.float32, [Z_SIZE])
epsilon = tf.placeholder(tf.float32, shape = [])

with tf.name_scope("d_discriminator_loss") as scope:
	img_attempt = dcgan_generator(z_node)
	print("img_attempt: {}".format(img_attempt.shape))
	x_hat = epsilon * true_img + (1 - epsilon) * img_attempt
	print("x_hat: {}".format(x_hat.shape))
	one = dcgan_discriminator(img_attempt)
	two = dcgan_discriminator(true_img, reuse=True)
	three = LAMBDA * ((tf.norm(tf.gradients(dcgan_discriminator(x_hat, reuse=True), x_hat)) - 1) ** 2)
	disc_loss = one - two + three

with tf.name_scope("g_generator_loss") as scope:
	gen_loss = -dcgan_discriminator(img_attempt, reuse=True)

t_vars = tf.trainable_variables()
d_vars = [var for var in t_vars if "d_" in var.name]
g_vars = [var for var in t_vars if "g_" in var.name]

with tf.name_scope("d_discriminator_train") as scope:
	disc_train = tf.train.AdamOptimizer(C, BETA_1, BETA_2).minimize(disc_loss, var_list=d_vars)

with tf.name_scope("g_generator_train") as scope:
	gen_train = tf.train.AdamOptimizer(C, BETA_1, BETA_2).minimize(gen_loss, var_list=g_vars)

init = tf.global_variables_initializer()

with tf.Session() as sess:
	print("Training...")
	writer = tf.summary.FileWriter(WRITER_PATH, sess.graph)
	sess.run(init)

	for epoch in range(EPOCHS):
		i = 0
		for training_image in training_images:
			training_image = np.reshape(training_image, IMAGE_DIMS)
			z_disc = get_z()
			eps = np.random.rand()
			w, d_loss = sess.run([disc_train, disc_loss], feed_dict = {z_node: z_disc, true_img: training_image, epsilon: eps}) #find disc loss, then update disc
			# print("Disc loss: {}".format(d_loss))
			if i % N_CRITIC == 0:
				z_gen = get_z()
				theta, g_loss = sess.run([gen_train, gen_loss], feed_dict = {z_node: z_gen}) #find gen loss, then update gen
				# print("Gen loss: {}".format(g_loss))
			i += 1
		if epoch % 1 == 0:#progessing samples
			z_test = get_z()
			out_image = sess.run(img_attempt, feed_dict = {z_node: z_test})
			out_image = np.reshape(out_image, [SQ_IMG_SIZE, SQ_IMG_SIZE, 3])
			plt.imsave("{}/epoch{}_sample.png".format(OUTPUT_PATH, epoch), out_image)
	print("Finished training!")

	#interpolation
	z1 = get_z()
	z2 = get_z()
	eps = np.arange(N_SAMPLES+1)/N_SAMPLES
	print(eps)
	i = 0
	for a in eps:
		tmp = a * z1 + (1 - a) * z2
		interp_image = sess.run(img_attempt, feed_dict={z_node: tmp})
		interp_image = np.reshape(interp_image, [SQ_IMG_SIZE, SQ_IMG_SIZE, 3])
		plt.imsave("{}/final_interp{}.png".format(OUTPUT_PATH, i), interp_image)
		i += 1

	#samples
	for s in range(N_SAMPLES):
		z_temp = get_z()
		out_image = sess.run(img_attempt, feed_dict = {z_node: z_temp})
		out_image = np.reshape(out_image, [SQ_IMG_SIZE, SQ_IMG_SIZE, 3])
		plt.imsave("{}/final_sample{}.png".format(OUTPUT_PATH, s), out_image)

	writer.close
