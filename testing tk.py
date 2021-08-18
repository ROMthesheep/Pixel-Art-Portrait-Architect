from tkinter import *

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

paramEntries = []

window = Tk()
window.title("PixelBreeder")
window.geometry("1000x800")

Label(window, text="Bienvenido a PixelBreeder. Por favor indica a continuacion los valores que quieres aplicar").grid(columnspan=10,row=0)
Label(window, text="Cuando tengas todos los valores listos pulsa el boton al final de la pantalla").grid(columnspan=10,row=1)
for idx, param in enumerate(creationParams):
  paramLabel = Label(window, text="{}: ".format(param), anchor="e").grid(column=0,row=idx+2)
  paramSpin = Spinbox(window, from_=0, to=1, width=10, increment=.05).grid(column=1,row=idx+2)
  paramEntries.append(paramSpin)



window.mainloop()