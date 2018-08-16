import os
import numpy as np
import tensorflow as tf
from tensorflow.keras import layers, regularizers, activations



class Mnasnet(tf.keras.Model):
	def __init__(self, num_classes,  alpha=1, **kwargs):
		super(Mnasnet, self).__init__(**kwargs)
		self.blocks = []

		self.conv_initial = conv(filters=32*alpha, kernel_size=3, strides=2)
		self.bn_initial = layers.BatchNormalization(epsilon=1e-3, momentum=0.999)

		# Frist block (non-identity) Conv+ DepthwiseConv
		self.conv1_block1 = depthwiseConv(depth_multiplier=1, kernel_size=3, strides=1)
		self.bn1_block1 = layers.BatchNormalization(epsilon=1e-3, momentum=0.999)

		self.conv2_block1 = conv(filters=16*alpha, kernel_size=1, strides=1)
		self.bn2_block1 = layers.BatchNormalization(epsilon=1e-3, momentum=0.999)

		# MBConv3 3x3
		self.blocks.append(MBConv_idskip(input_filters=16*alpha, filters=24, kernel_size=3, strides=2, filters_multiplier=3, alpha=alpha))
		self.blocks.append(MBConv_idskip(input_filters=24*alpha, filters=24, kernel_size=3, strides=1, filters_multiplier=3, alpha=alpha))
		self.blocks.append(MBConv_idskip(input_filters=24*alpha, filters=24, kernel_size=3, strides=1, filters_multiplier=3, alpha=alpha))

		# MBConv3 5x5
		self.blocks.append(MBConv_idskip(input_filters=24*alpha, filters=40, kernel_size=5, strides=2, filters_multiplier=3, alpha=alpha))
		self.blocks.append(MBConv_idskip(input_filters=40*alpha, filters=40, kernel_size=5, strides=1, filters_multiplier=3, alpha=alpha))
		self.blocks.append(MBConv_idskip(input_filters=40*alpha, filters=40, kernel_size=5, strides=1, filters_multiplier=3, alpha=alpha))
		# MBConv6 5x5
		self.blocks.append(MBConv_idskip(input_filters=40*alpha, filters=80, kernel_size=5, strides=2, filters_multiplier=6, alpha=alpha))
		self.blocks.append(MBConv_idskip(input_filters=80*alpha, filters=80, kernel_size=5, strides=1, filters_multiplier=6, alpha=alpha))
		self.blocks.append(MBConv_idskip(input_filters=80*alpha, filters=80, kernel_size=5, strides=1, filters_multiplier=6, alpha=alpha))

		# MBConv6 3x3
		self.blocks.append(MBConv_idskip(input_filters=80*alpha, filters=96, kernel_size=3, strides=1, filters_multiplier=6, alpha=alpha))
		self.blocks.append(MBConv_idskip(input_filters=96*alpha, filters=96, kernel_size=3, strides=1, filters_multiplier=6, alpha=alpha))

		# MBConv6 5x5
		self.blocks.append(MBConv_idskip(input_filters=96*alpha, filters=192, kernel_size=5, strides=2, filters_multiplier=6, alpha=alpha))
		self.blocks.append(MBConv_idskip(input_filters=192*alpha, filters=192, kernel_size=5, strides=1, filters_multiplier=6, alpha=alpha))
		self.blocks.append(MBConv_idskip(input_filters=192*alpha, filters=192, kernel_size=5, strides=1, filters_multiplier=6, alpha=alpha))
		self.blocks.append(MBConv_idskip(input_filters=192*alpha, filters=192, kernel_size=5, strides=1, filters_multiplier=6, alpha=alpha))
		# MBConv6 3x3
		self.blocks.append(MBConv_idskip(input_filters=192*alpha, filters=320, kernel_size=3, strides=1, filters_multiplier=6, alpha=alpha))

		# Last convolution
		self.conv_last = conv(filters=1152*alpha, kernel_size=1, strides=1)
		self.bn_last = layers.BatchNormalization(epsilon=1e-3, momentum=0.999)
		# Pool + FC
		self.avg_pool =  layers.GlobalAveragePooling2D()
		self.fc = layers.Dense(num_classes)


	def call(self, inputs, training=None, mask=None):
		out = self.conv_initial(inputs)
		out = self.bn_initial(out, training=training)
		out = tf.nn.relu(out)

		out = self.conv1_block1(out)
		out = self.bn1_block1(out, training=training)
		out = tf.nn.relu(out)

		out = self.conv2_block1(out)
		out = self.bn2_block1(out, training=training)
		out = tf.nn.relu(out)

		# forward pass through all the blocks
		for block in self.blocks:
			out = block(out, training=training)

		out = self.conv_last(out)
		out = self.bn_last(out, training=training)
		out = tf.nn.relu(out)

		out = self.avg_pool(out)
		out = self.fc(out)
		
		return out




# This function is taken from the original tf repo.
# It ensures that all layers have a channel number that is divisible by 8
# It can be seen here:
# https://github.com/tensorflow/models/blob/master/research/slim/nets/mobilenet/mobilenet.py
def _make_divisible(v, divisor=8, min_value=None):
	if min_value is None:
		min_value = divisor
	new_v = max(min_value, int(v + divisor / 2) // divisor * divisor)
	# Make sure that round down does not go down by more than 10%.
	if new_v < 0.9 * v:
		new_v += divisor
	return new_v


# convolution
def conv(filters, kernel_size, strides=1):
	return layers.Conv2D(filters, kernel_size, strides=strides, padding='same', use_bias=False,
								kernel_regularizer=regularizers.l2(l=0.0003))
# Depthwise convolution
def depthwiseConv(kernel_size, strides=1, depth_multiplier=1):
	return layers.DepthwiseConv2D(kernel_size, strides=strides, depth_multiplier=depth_multiplier,
								padding='same', use_bias=False, kernel_regularizer=regularizers.l2(l=0.0003))

class MBConv_idskip(tf.keras.Model):

	def __init__(self, input_filters, filters, kernel_size, strides=1, filters_multiplier=1, alpha=1):
		super(MBConv_idskip, self).__init__()

		self.filters = filters
		self.kernel_size = kernel_size
		self.strides = strides
		self.filters_multiplier = filters_multiplier
		self.alpha = alpha

		self.depthwise_conv_filters = _make_divisible(input_filters) 
		self.pointwise_conv_filters = _make_divisible(filters * alpha)

		#conv1
		self.conv1 = conv(filters=self.depthwise_conv_filters*filters_multiplier, kernel_size=1, strides=1)
		self.bn1 = layers.BatchNormalization(epsilon=1e-3, momentum=0.999)

		#depthwiseconv2
		self.conv2 = depthwiseConv(depth_multiplier=1, kernel_size=kernel_size, strides=strides)
		self.bn2 = layers.BatchNormalization(epsilon=1e-3, momentum=0.999)

		#conv3
		self.conv3 = conv(filters=self.pointwise_conv_filters, kernel_size=1, strides=1)
		self.bn3 = layers.BatchNormalization(epsilon=1e-3, momentum=0.999)


	def call(self, inputs, training=None):

		x = self.conv1(inputs)
		x = self.bn1(x, training=training)
		x = tf.nn.relu(x)

		x = self.conv2(x)
		x = self.bn2(x, training=training)
		x = tf.nn.relu(x)

		x = self.conv3(x)
		x = self.bn3(x, training=training)
		
		# Residual/Identity connection if possible
		if self.strides==1 and x.shape[3] == inputs.shape[3]:
			return  layers.add([inputs, x])
		else: 
			return x

