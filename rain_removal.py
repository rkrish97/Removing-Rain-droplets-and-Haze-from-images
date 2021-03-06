# -*- coding: utf-8 -*-
"""Rain removal

Automatically generated by Colaboratory.

Original file is located at
    https://colab.research.google.com/drive/1UW5jQV2x3mFSRem5GC9KGgwy1yjoMhaG
"""

!pip install tensorflow==1.15

from google.colab import drive
drive.mount('/content/drive')

"""# Training"""

def diff_x(input, r):
  assert input.shape.ndims == 4

  left   = input[:, :,         r:2 * r + 1]
  middle = input[:, :, 2 * r + 1:         ] - input[:, :,           :-2 * r - 1]
  right  = input[:, :,        -1:         ] - input[:, :, -2 * r - 1:    -r - 1]

  output = tf.concat([left, middle, right], axis=2)

  return output

def diff_y(input, r):
  assert input.shape.ndims == 4

  left   = input[:, :, :,         r:2 * r + 1]
  middle = input[:, :, :, 2 * r + 1:         ] - input[:, :, :,           :-2 * r - 1]
  right  = input[:, :, :,        -1:         ] - input[:, :, :, -2 * r - 1:    -r - 1]

  output = tf.concat([left, middle, right], axis=3)

  return output

def box_filter(x, r):
  assert x.shape.ndims == 4

  return diff_y(tf.cumsum(diff_x(tf.cumsum(x, axis=2), r), axis=3), r)

def guided_filter(x, y, r, eps=1e-8, nhwc=False):
  assert x.shape.ndims == 4 and y.shape.ndims == 4

  # data format
  if nhwc:
      x = tf.transpose(x, [0, 3, 1, 2])
      y = tf.transpose(y, [0, 3, 1, 2])

  # shape check
  x_shape = tf.shape(x)
  y_shape = tf.shape(y)

  assets = [tf.assert_equal(   x_shape[0],  y_shape[0]),
            tf.assert_equal(  x_shape[2:], y_shape[2:]),
            tf.assert_greater(x_shape[2:],   2 * r + 1),
            tf.Assert(tf.logical_or(tf.equal(x_shape[1], 1),
                                    tf.equal(x_shape[1], y_shape[1])), [x_shape, y_shape])]

  with tf.control_dependencies(assets):
      x = tf.identity(x)

  # N
  N = box_filter(tf.ones((1, 1, x_shape[2], x_shape[3]), dtype=x.dtype), r)

  # mean_x
  mean_x = box_filter(x, r) / N
  # mean_y
  mean_y = box_filter(y, r) / N
  # cov_xy
  cov_xy = box_filter(x * y, r) / N - mean_x * mean_y
  # var_x
  var_x  = box_filter(x * x, r) / N - mean_x * mean_x

  # A
  A = cov_xy / (var_x + eps)
  # b
  b = mean_y - A * mean_x

  mean_A = box_filter(A, r) / N
  mean_b = box_filter(b, r) / N

  output = mean_A * x + mean_b

  if nhwc:
      output = tf.transpose(output, [0, 2, 3, 1])

  return output

import os
import re
import time
import numpy as np
import tensorflow as tf
import matplotlib.pyplot as plt
import random
from random import randint

tf.reset_default_graph()

##################### Network parameters ###################################
num_feature = 16             # number of feature maps
num_channels = 3             # number of input's channels 
patch_size = 64              # patch size 
KernelSize = 3               # kernel size 
learning_rate = 0.15          # learning rate
iterations = int(2*1e5)    # iterations
batch_size = 20              # batch size
save_model_path = "/content/drive/My Drive/" # saved model's path
model_name = 'd_model-epoch'   # saved model's name
############################################################################


# randomly select image patches

def _parse_function(rainy, label):  
  rainy = tf.cast(rainy, tf.float32)/255.0
  label = tf.cast(label, tf.float32)/255.0
  t = randint(0,10)
  rainy = tf.image.random_crop(rainy, [patch_size, patch_size ,3],seed = t)   # randomly select patch
  label = tf.image.random_crop(label, [patch_size, patch_size ,3],seed = t)   
  return rainy, label


# network structure
def inference(images, is_training):
  regularizer = tf.contrib.layers.l2_regularizer(scale = 1e-10)
  initializer = tf.contrib.layers.xavier_initializer()

  base = guided_filter(images, images, 15, 1, nhwc=True) # using guided filter for obtaining base layer
  detail = images - base   # detail layer

  #  layer 1
  with tf.variable_scope('layer_1'):
        output = tf.layers.conv2d(detail, num_feature, KernelSize, padding = 'same', kernel_initializer = initializer, 
                                  kernel_regularizer = regularizer, name='conv_1')
        output = tf.layers.batch_normalization(output, training=is_training, name='bn_1')
        output_shortcut = tf.nn.relu(output, name='relu_1')

  #  layers 2 to 25
  for i in range(12):
      with tf.variable_scope('layer_%d'%(i*2+2)):	
            output = tf.layers.conv2d(output_shortcut, num_feature, KernelSize, padding='same', kernel_initializer = initializer, 
                                      kernel_regularizer = regularizer, name=('conv_%d'%(i*2+2)))
            output = tf.layers.batch_normalization(output, training=is_training, name=('bn_%d'%(i*2+2)))	
            output = tf.nn.relu(output, name=('relu_%d'%(i*2+2)))


      with tf.variable_scope('layer_%d'%(i*2+3)): 
            output = tf.layers.conv2d(output, num_feature, KernelSize, padding='same', kernel_initializer = initializer,
                                      kernel_regularizer = regularizer, name=('conv_%d'%(i*2+3)))
            output = tf.layers.batch_normalization(output, training=is_training, name=('bn_%d'%(i*2+3)))
            output = tf.nn.relu(output, name=('relu_%d'%(i*2+3)))

      output_shortcut = tf.add(output_shortcut, output)   # shortcut

  # layer 26
  with tf.variable_scope('layer_26'):
        output = tf.layers.conv2d(output_shortcut, num_channels, KernelSize, padding='same',   kernel_initializer = initializer, 
                                  kernel_regularizer = regularizer, name='conv_26')
        neg_residual = tf.layers.batch_normalization(output, training=is_training, name='bn_26')

  final_out = tf.add(images, neg_residual)

  return final_out

# Commented out IPython magic to ensure Python compatibility.
ra = np.load('/content/drive/My Drive/array/rainy_train2.npy')
cl = np.load('/content/drive/My Drive/array/clear_train2.npy')

dataset = tf.data.Dataset.from_tensor_slices((ra, cl))
dataset = dataset.map(_parse_function)    
dataset = dataset.prefetch(buffer_size = batch_size*10)
dataset = dataset.batch(batch_size).repeat()   
iterator = dataset.make_one_shot_iterator()

rainy, labels = iterator.get_next()     


outputs = inference(rainy, is_training = True)
loss = tf.reduce_mean(tf.square(labels - outputs))    # MSE loss


lr_ = learning_rate
lr = tf.placeholder(tf.float32 ,shape = [])  

update_ops = tf.get_collection(tf.GraphKeys.UPDATE_OPS)
with tf.control_dependencies(update_ops):
    train_op =  tf.train.MomentumOptimizer(lr, 0.9).minimize(loss) 


all_vars = tf.trainable_variables()   
g_list = tf.global_variables()
bn_moving_vars = [g for g in g_list if 'moving_mean' in g.name]
bn_moving_vars += [g for g in g_list if 'moving_variance' in g.name]
all_vars += bn_moving_vars
print("Total parameters' number: %d" %(np.sum([np.prod(v.get_shape().as_list()) for v in all_vars])))  
saver = tf.train.Saver(var_list=all_vars, max_to_keep=5)


config = tf.ConfigProto()
#config.gpu_options.per_process_gpu_memory_fraction = 0.8 # GPU setting
#config.gpu_options.allow_growth = True
init =  tf.group(tf.global_variables_initializer(), 
                      tf.local_variables_initializer())  

with tf.Session(config=config) as sess:      
   
  sess.run(init)
  tf.get_default_graph().finalize()

  '''if tf.train.get_checkpoint_state('./model/'):   # load previous trained models
    ckpt = tf.train.latest_checkpoint('./model/')
    saver.restore(sess, ckpt)
    ckpt_num = re.findall(r'(\w*[0-9]+)\w*',ckpt)
    start_point = int(ckpt_num[0]) + 1   
    print("successfully load previous model")

  else:   # re-training if no previous trained models
    start_point = 0    
    print("re-training")'''


  check_data, check_label = sess.run([rainy, labels])
  print("Check patch pair:")  
  plt.subplot(1,2,1)     
  plt.imshow(check_data[0,:,:,:])
  plt.title('input')         
  plt.subplot(1,2,2)    
  plt.imshow(check_label[0,:,:,:])
  plt.title('ground truth')        
  plt.show()


  start = time.time()  

  for j in range(iterations):   #  iterations
    if j+1 > int(1e5):
      lr_ = 0.1
    #if j+1 > int(2e5):
     # lr_ = learning_rate*0.01
    #if j+1 > int(3e5):
     # lr_ = learning_rate*0.001            
          

    _,Training_Loss = sess.run([train_op,loss], feed_dict={lr: lr_}) # training
    print ('%d / %d iteraions, learning rate = %.3f, Training Loss = %.4f' 
#           % (j+1, iterations, lr_, Training_Loss))
    if np.mod(j+1,100) == 0 and j != 0:
      save_path_full = os.path.join(save_model_path, model_name) # save model
      saver.save(sess, save_path_full, global_step = j+1, write_meta_graph=False)
          
  print('Training is finished.')
sess.close()

"""# Testing"""

import os
import skimage
from skimage import io
import numpy as np
import tensorflow as tf
import matplotlib.pyplot as plt
from keras.utils.vis_utils import plot_model
import cv2
import glob


num_img = 58
tf.reset_default_graph()

model_path = '/content/drive/My Drive/'
pre_trained_model_path = './model/trained/model'




def _parse_function(rainy):     
  rainy = tf.cast(rainy, tf.float32)/255.0 
  return rainy 


if __name__ == '__main__':
  cou = 0
  for k in range(1,11):
    tf.reset_default_graph()
    r = []
    f = '/content/dehazed_image-{k}.png'.format(k=k)
    r.append(np.array(cv2.imread(f)))
    r = np.array(r)
    #ra2 = np.load('/content/drive/My Drive/array/rainy_test2.npy')     
    dataset = tf.data.Dataset.from_tensor_slices(r)
    dataset = dataset.map(_parse_function)    
    #dataset = dataset.prefetch(buffer_size=10)
    dataset = dataset.batch(batch_size=1).repeat()  
    iterator = dataset.make_one_shot_iterator()

    rain = iterator.get_next() 


    output = inference(rain, is_training = False)
    output = tf.clip_by_value(output, 0., 1.)
    output = output[0,:,:,:]

    config = tf.ConfigProto()  
    saver = tf.train.Saver()

    with tf.Session(config=config) as sess: 
          
      if tf.train.get_checkpoint_state(model_path):  
        #ckpt = tf.train.latest_checkpoint(model_path)
        ckpt_name = "d_model-epoch-200000"
        path = os.path.join('/content/drive/My Drive/', ckpt_name) 
        saver.restore(sess, path)
        print ("Loading model")
      for i in range(1):     
        derained, ori = sess.run([output, rain])  
                    
        derained = np.uint8(derained* 255.)
        derained = cv2.cvtColor(derained, cv2.COLOR_BGR2RGB)
        name = "derain-{k}".format(k=k)
        skimage.io.imsave("/content/drive/My Drive/test_real2/" + name +'.png', derained)         
        print('%d / %d images processed' % (i+1,num_img))
                
    
    sess.close()   
  print('All done')
  plt.subplot(1,2,1)     
  ori[0,:,:,:] = cv2.cvtColor(ori[0,:,:,:], cv2.COLOR_BGR2RGB)
  plt.imshow(ori[0,:,:,:])          
  plt.title('rainy')
  plt.subplot(1,2,2)    
  plt.imshow(derained)
  plt.title('derained')
  plt.show()

import skimage
from skimage.measure import compare_ssim
de = cv2.imread('/content/drive/My Drive/test_real2/derain-4.png')
raa = cv2.imread('/content/drive/My Drive/test_real/C-130.jpg')
deha = cv2.imread('/content/dehazed_image-10.png')
plt.imshow(de)

plt.figure()
plt.imshow(raa)

plt.figure()
plt.imshow(deha)
(sc1, diff) = compare_ssim(de, raa, full = True, multichannel = True)
print(sc1)

import os
import skimage
from skimage import io
import numpy as np
import tensorflow as tf
import matplotlib.pyplot as plt
from keras.utils.vis_utils import plot_model
import cv2
import glob

r = []
for f in glob.glob('/content/A-F-17.jpg'):
  r.append(np.array(cv2.imread(f)))

r = np.array(r)


num_img = 58
tf.reset_default_graph()

model_path = '/content/drive/My Drive/'
pre_trained_model_path = './model/trained/model'




def _parse_function(rainy):     
  rainy = tf.cast(rainy, tf.float32)/255.0 
  return rainy 


if __name__ == '__main__':
   
  ra2 = np.load('/content/drive/My Drive/array/rainy_test2.npy')     
  dataset = tf.data.Dataset.from_tensor_slices(r)
  dataset = dataset.map(_parse_function)    
  #dataset = dataset.prefetch(buffer_size=10)
  dataset = dataset.batch(batch_size=1).repeat()  
  iterator = dataset.make_one_shot_iterator()

  rain = iterator.get_next() 


  output = inference(rain, is_training = False)
  output = tf.clip_by_value(output, 0., 1.)
  output = output[0,:,:,:]

  config = tf.ConfigProto()  
  saver = tf.train.Saver()

  with tf.Session(config=config) as sess: 
        
    if tf.train.get_checkpoint_state(model_path):  
      #ckpt = tf.train.latest_checkpoint(model_path)
      ckpt_name = "d_model-epoch-200000"
      path = os.path.join('/content/drive/My Drive/', ckpt_name) 
      saver.restore(sess, path)
      print ("Loading model")

    for i in range(1):     
      derained, ori = sess.run([output, rain])  
                  
      derained = np.uint8(derained* 255.)
      derained = cv2.cvtColor(derained, cv2.COLOR_BGR2RGB)
      name = "derained-{i}".format(i=i)
      skimage.io.imsave("/content/drive/My Drive/test_real/" + name +'.png', derained)         
      print('%d / %d images processed' % (i+1,num_img))
              
  print('All done')
  sess.close()   

  plt.subplot(1,2,1)     
  ori[0,:,:,:] = cv2.cvtColor(ori[0,:,:,:], cv2.COLOR_BGR2RGB)
  plt.imshow(ori[0,:,:,:])          
  plt.title('rainy')
  plt.subplot(1,2,2)    
  plt.imshow(derained)
  plt.title('derained')
  plt.show()

i = [36,18,16, 27,54,55]
import skimage
from skimage import io
from google.colab.patches import cv2_imshow
from skimage.measure import compare_ssim
import matplotlib.pyplot as plt
import cv2

for j,k in enumerate(i):
  im200 = cv2.imread('/content/drive/My Drive/d_model/d_fig-{i}.png'.format(i=k))

  im2 = np.load('/content/drive/My Drive/array/clear_test2.npy')
  im2[k,:,:,:] = cv2.cvtColor(im2[k,:,:,:], cv2.COLOR_BGR2RGB)

  ra2 = np.load('/content/drive/My Drive/array/rainy_test2.npy') 
  ra2[k,:,:,:] = cv2.cvtColor(ra2[k,:,:,:], cv2.COLOR_BGR2RGB)

  (sc1, diff) = compare_ssim(im2[k,:,:,:], im200, full = True, multichannel = True)

  (sc2, diff) = compare_ssim(im2[k,:,:,:], ra2[k,:,:,:], full = True, multichannel = True)

  plt.subplot(3,len(i),j+1)
  plt.axis('off')
  plt.imshow(ra2[k,:,:,:]) 
  #plt.title("Rainy, SSIM: {:.2f}".format(sc2))

  plt.subplot(3,len(i),j+len(i)+1)
  plt.axis('off')
  plt.imshow(im200)
  #plt.title("Derained, SSIM: {:.2f}".format(sc1))

  plt.subplot(3,len(i),j+2*len(i)+1)
  plt.axis('off')
  plt.imshow(im2[k,:,:,:])
  #plt.title("Clear ground truth")

plt.tight_layout(0.5) 
plt.savefig("plot.png")

clear = []
dehaze = []
hazy = []
import cv2

for i in range(1,7):
  c = cv2.imread('/content/drive/My Drive/CLEAR_IMAGES/{i}.jpg'.format(i=i))
  clear.append(cv2.resize(c,(480,480)))
  d = cv2.imread('/content/drive/My Drive/DEHAZED/{i}.jpg'.format(i=i))
  dehaze.append(cv2.resize(d,(480,480)))
  h = cv2.imread('/content/drive/My Drive/HAZY_IMAGES/{i}.jpg'.format(i=i))
  hazy.append(cv2.resize(h,(480,480)))

for j,i in enumerate([1,4,5]):
  (sc1, diff) = compare_ssim(clear[i], hazy[i], full = True, multichannel = True)

  (sc2, diff) = compare_ssim(clear[i], dehaze[i], full = True, multichannel = True)

  plt.subplot(3,3,j+1)
  plt.axis('off')
  plt.imshow(hazy[i]) 
  plt.title("Hazy, SSIM: {:.2f}".format(sc1))

  plt.subplot(3,3,j+4)
  plt.axis('off')
  plt.imshow(dehaze[i])
  plt.title("Dehazed, SSIM: {:.2f}".format(sc2))

  plt.subplot(3,3,j+7)
  plt.axis('off')
  plt.imshow(clear[i])
  plt.title("Clear ground truth")

plt.tight_layout() 
plt.savefig("plot.png")

"""# Dehazing"""

from matplotlib import image
import numpy as np
import numpy
from sklearn.model_selection import train_test_split
import tensorflow as tf
from PIL import Image
import glob
from keras.layers import ReLU
from google.colab.patches import cv2_imshow



from keras.models import Sequential, load_model
from keras.layers import Conv2D, MaxPooling2D
from keras.layers import Activation, Dropout, Flatten, Dense, Lambda, Input
from keras import backend as K
import cv2, numpy as np
import glob
from keras.activations import relu 
import keras as keras
from keras.models import Model
import tensorflow as tf


from keras.layers import Input, concatenate, Conv2D, MaxPooling2D, Conv2DTranspose
from keras.optimizers import Adam
from keras.callbacks import ModelCheckpoint
from keras import backend as K
img_width, img_height = 640, 480
import os
from keras.callbacks import EarlyStopping, ModelCheckpoint, TensorBoard
from  sklearn.model_selection import train_test_split

#from tensorflow.python import debug as tf_debug
import imageio
import glob
from skimage import transform as tf

from scipy import ndimage
import matplotlib.pyplot as plt
import matplotlib.image as plt_img
import scipy
import scipy
import skimage
import re
#import LRFinder
import math as m


from keras import backend as K
from pathlib import Path
from keras import optimizers

import numpy as np

from keras import backend as K
from skimage.measure import compare_ssim, compare_psnr

import cv2
import numpy as np
from matplotlib import pyplot as plt

def haze_net(X):
  weight_decay = 1e-4
  conv1 = Conv2D(3,(1,1),padding="SAME",activation="relu",use_bias=True,kernel_initializer=tf.initializers.random_normal(),
                kernel_regularizer=tf.keras.regularizers.l2(weight_decay))(X)
  conv2 = Conv2D(3,(3,1),padding="SAME",activation="relu",use_bias=True,kernel_initializer=tf.initializers.random_normal(),
                kernel_regularizer=tf.keras.regularizers.l2(weight_decay))(conv1)
  concat1 = tf.concat([conv1,conv2],axis=-1)
  
  conv3 = Conv2D(3,(5,1),padding="SAME",activation="relu",use_bias=True,kernel_initializer=tf.initializers.random_normal(),
                kernel_regularizer=tf.keras.regularizers.l2(weight_decay))(concat1)
  concat2 = tf.concat([conv2,conv3],axis=-1)
  
  conv4 = Conv2D(3,(7,1),padding="SAME",activation="relu",use_bias=True,kernel_initializer=tf.initializers.random_normal(),
                kernel_regularizer=tf.keras.regularizers.l2(weight_decay))(concat2)
  concat3 = tf.concat([conv1,conv2,conv3,conv4],axis=-1)
  
  conv5 = Conv2D(3,(3,1),padding="SAME",activation="relu",use_bias=True,kernel_initializer=tf.initializers.random_normal(),
                kernel_regularizer=tf.keras.regularizers.l2(weight_decay))(concat3)
  K = conv5
  
  output = ReLU(max_value=1.0)(tf.math.multiply(K,X) - K + 1.0)
  #output = output / 255.0
  
  return output

import os
import skimage
from skimage import io
import numpy as np
import tensorflow as tf
import matplotlib.pyplot as plt
from keras.utils.vis_utils import plot_model
import cv2
import glob

def _parse_function(rainy):     
  rainy = tf.cast(rainy, tf.float32)/255.0 
  return rainy 

for h in range(1,11):
  f = '/content/drive/My Drive/dehaaa/d-{h}.png'.format(h=h)
  tf.reset_default_graph()
  r = []
  r.append(np.array(cv2.imread(f)))
  r = np.array(r)
  #ra2 = np.load('/content/drive/My Drive/array/rainy_test2.npy')     
  dataset = tf.data.Dataset.from_tensor_slices(r)
  dataset = dataset.map(_parse_function)    
  #dataset = dataset.prefetch(buffer_size=10)
  dataset = dataset.batch(batch_size=1).repeat()  
  iterator = dataset.make_one_shot_iterator()

  rain = iterator.get_next() 
  dehazed_X = haze_net(rain)
  dehazed_X = tf.clip_by_value(dehazed_X, 0., 1.)
  dehazed_X = dehazed_X[0,:,:,:]
  saver = tf.train.Saver()
  from PIL import Image  
  file_types = ['jpeg','jpg']
  

  with tf.Session() as sess:
    saver.restore(sess, '/content/model_checkpoint_9.ckpt')
    #f = []
    #for i in range(58):
    #  f.append('/content/drive/My Drive/imag/fig-{i}.png'.format(i = i))

    #X = tf.placeholder(shape=(None,480,640,3),dtype=tf.float32)
    #Y = tf.placeholder(shape=(None,480,640,3),dtype=tf.float32)
    
    #for path in f:
      #image_label = path.split(test_input_folder)[-1][1:]
      #image = Image.open(path)
      #image = image.resize((640, 480))
      #image = np.asarray(image) / 255.0
      #image = image.reshape((1,) + image.shape)
    for i in range(1):
      dehazed_image,ori = sess.run([dehazed_X,rain])
      
      
      #fig, axes = plt.subplots(nrows=1, ncols=2,figsize=(10,10))
      #axes[0].imshow(image[0])
      #axes[1].imshow(dehazed_image[0])
      #fig.tight_layout()
      dehazed_image = np.uint8(dehazed_image* 255.)
      dehazed_image = cv2.cvtColor(dehazed_image, cv2.COLOR_BGR2RGB)
      name = "de-{h}".format(h=h)
      skimage.io.imsave("/content/drive/My Drive/dehaaa/" + name +'.png', dehazed_image)

i = [3]
import skimage
from skimage import io
from google.colab.patches import cv2_imshow
from skimage.measure import compare_ssim
import matplotlib.pyplot as plt
import cv2

for j,k in enumerate(i):
  if k==3:
    im200 = cv2.imread('/content/drive/My Drive/dehaaa/d-3.png')
    im200 = cv2.cvtColor(im200, cv2.COLOR_BGR2RGB)
  else:
    im200 = cv2.imread('/content/drive/My Drive/dehaaa/d-{i}.png'.format(i=k))
    im200 = cv2.cvtColor(im200, cv2.COLOR_BGR2RGB)

  ra2 = cv2.imread('/content/drive/My Drive/dehaaa/{k}.png'.format(k=k)) 
  ra2 = cv2.cvtColor(ra2, cv2.COLOR_BGR2RGB)

  im = cv2.imread('/content/drive/My Drive/dehaaa/de-3.png')
  im = cv2.cvtColor(im, cv2.COLOR_BGR2RGB)

  plt.subplot(3,len(i),j+1)
  plt.axis('off')
  plt.imshow(ra2) 
  plt.title("Hazy")

  plt.subplot(3,len(i),j+len(i)+1)
  plt.axis('off')
  plt.imshow(im200)
  plt.title("Dehazed")

  plt.subplot(3,len(i),j+len(i)+2)
  plt.axis('off')
  plt.imshow(im)
  plt.title("Dehazed twice")


plt.tight_layout(0.5) 
plt.savefig("plot_deh.png")