from skimage import io
from pyxelate import Pyx, Pal


def run(downSample, palette, dither):
  image = io.imread("imgFromAB.jpg")  

  downsample_by = downSample
  pyx = Pyx(factor=downsample_by, palette=Pal.from_hex(palette), dither=dither)
  pyx.fit(image)
  new_image = pyx.transform(image)
  io.imsave("pixel.png", new_image)
