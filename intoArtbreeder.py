from typing import Dict
from selenium.webdriver.firefox.options import Options as FirefoxOptions
from selenium import webdriver
from selenium.webdriver.firefox.webdriver import WebDriver
from time import perf_counter, sleep
import urllib.request

def initiateBrowser():
  options = FirefoxOptions()
  # options.add_argument("--headless")
  driver = webdriver.Firefox(options=options, executable_path="geckodriver.exe")
  print("liberando al gecko")
  return driver

def navigateToTarget(browser: WebDriver, paths, credentials):
  browser.get("https://www.artbreeder.com/")
  browser.find_element_by_xpath(paths["navigationPaths"]["startBTN"]).click()
  browser.find_element_by_xpath(paths["navigationPaths"]["loginBTN"]).click()
  browser.find_element_by_xpath(paths["navigationPaths"]["emailINP"]).send_keys(credentials["email"])
  browser.find_element_by_xpath(paths["navigationPaths"]["passINP"]).send_keys(credentials["password"])
  browser.find_element_by_xpath(paths["navigationPaths"]["loginFormBTN"]).click()
  print("logeando en Artbreeder")
  sleep(2)
  browser.find_element_by_xpath(paths["navigationPaths"]["createBTN"]).click()
  browser.find_element_by_xpath(paths["navigationPaths"]["portraitBTN"]).click()
  browser.find_element_by_xpath(paths["navigationPaths"]["composeBTN"]).click()
  sleep(2)
  print("Accediendo a la herramientra de creacion")

def enterParams(browser: WebDriver, paths, creationParams: Dict):
  for param in creationParams:
    browser.find_element_by_xpath(paths["creationPaths"][param]).clear()
    browser.find_element_by_xpath(paths["creationPaths"][param]).send_keys(creationParams[param])
  print("Valores colocados")
  sleep(1)
  print("refrescando retratos")
  browser.find_element_by_xpath(paths["navigationPaths"]["refreshPortraits"]).click()


def storePortraits(browser: WebDriver, paths):
  print("descargando la primera imagen...", end="")
  img = ""

  while len(img) < 80:
    sleep(3)
    print("..", end="")
    img = browser.find_element_by_xpath(paths["portraitPath"]).get_attribute('src')
    
  print("\nimagen descargada")
  urllib.request.urlretrieve(img, "imgFromAB.jpg")

  
  




