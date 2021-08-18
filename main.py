from intoArtbreeder import *
from PyxelateRutine import run
import json
import enum

class DitherTypes(enum.Enum):
  none = "none"
  naive = "naive"
  bayer = "bayer"
  floyd = "floyd"
  atkinson = "atkinson"

creationParams = {
  "chaos" : "0.7",
  "age" : "0",
  "gender" : "0",
  "width" : "0",
  "height" : "0",
  "yaw" : "0",
  "pitch" : "0",
  "asian" : "0",
  "indian": "0",
  "black": "0",
  "white" : "0",
  "middleEast": "0.420",
  "latino" : "0",
  "art" : "0",
  "red" : "0",
  "green" : "0",
  "blue" : "0",
  "hue" : "0",
  "sat" : "0",
  "bright" : "0",
  "sharp" : "0",
  "happy" : "0",
  "angry" : "0",
  "blueEyes" : "0",
  "earrings" : "0",
  "eyesOpen" : "0",
  "mouthOpen" : "0",
  "blackHair" : "0",
  "blondeHair" : "0",
  "brownHair" : "0",
  "makeup" : "0",
  "glasses" : "0",
  "facialHair" : "0",
  "hat" : "0"
}

dither = DitherTypes.none
myPal = [
  "#48941C",
  "#2B3DE0",
  "#5FE014",
  "#E05E2B",
  "#942E06"
]
downscale = 16

paths = json.load(open('adresses.json'))
cred = json.load(open('credentials.json'))
browser = initiateBrowser()
navigateToTarget(browser, paths, cred)
enterParams(browser, paths, creationParams)
storePortraits(browser, paths["navigationPaths"])

run(downscale, myPal, dither)
