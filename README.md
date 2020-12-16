# Image-Dehazing-using-AOD-Net
In this project, we will be performing Hazy Image Recovery
using the All In One Image Dehazing (AOD) convolutional
neural network (CNN) to dehaze an image and an end-toend Deep Neural Network architecture to remove rain streaks
from single images. The AOD network directly generates the
dehazed image through a light-weight CNN, without estimating the transmission matrix and the atmospheric light separately as most previous models have done. Such a network
makes it easy to embed the AOD network into other deep
models for improving high-level tasks on hazy images. For
the rain removal task, we implement a deep Residual neural
network (Resnet) to make the learning process easier by reducing the mapping range between the input and the output.
Further, we use high-frequency detail images for training the
network instead of using the images directly. By doing so we
focus on the high-frequency rain streaks in the image. Previously developed methods are based on separating the rain
streaks from the images using only low-level features. These
methods face difficulty in removing the rain streaks when the
structure of the rain is similar to the object in the scene.
