#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
SCHISM Model Builder (SCHISMMB)

SCHISMMB is the container of the the classes and methods to build the inputs 
for SCHISM Modelling system. 

The model input is first build using the following objects - 
    Hgrid:      Horizontal grid
    Vgrid:      Vertical grid
    Bctide:     Boundary conditions
    Roughness:  Roughness conditions
    
These objects are passed to the Project object with a directory to create the 
files to run the model.

@author: Md. Jamal Uddin Khan
@email: jamal.khan@legos.obs-mip.fr
"""
import os
import numpy as np

class Project(object):
    """
    SCHISM model project object. It only contains Path information regarding
    the model project and passed to the model object for further processing.
    """
    def __init__(self, path = None):
        """ Initialize the project folder """
        self.path = path
        if os.access(path, os.F_OK):
            self.direxist = True
            print "Directory exist! All files will be overwritten."
        else:
            os.mkdir(path)
            print "Project directory created!"
            self.direxist = True
            
    def loadhgrid(self, hgrid):
        """ Load the hgrid into the project 
        hgrid is an object of Hgrid class.
        """
        self.hgrid = hgrid
            
    def delete(self):
        """ Delete project """
        os.rmdir(self.path)

    def createwwmbound(self, flags):
        """ Create the WWM complient boundary file named wwmbound.gr3
WWMIII requires an input indicating the boundary location. The fil is a Gr3 type file with following flags in the data section - 

        0 : Not on the boundary
        2 : Active boundary (Direchlet)
        3 : Neumann (0 gradient)

createwwmbound takes the hgrid file and corresponding boundary flag as input and save the wwmbound.gr3 at a specified location.        
        """


class Hgrid(object):
    """
    SCHISM hgrid.gr3 object. This object loads the hgrid.gr3 file, breaks it in
    it's subcomponent, and store it for the model object to use.
    
    Grid or *.gr3 is essentially the fort.14 file format in ADCIRC model in SMS. 
    The intended way for this model is to provide the original file from SMS.
    """
    def __init__(self, path = None):
        self.path = path
        if os.access(self.path, os.F_OK):
            self.read()
        else:
            print('Check the hgrid.gr3 file location')
        
    def read(self): 
        """ Read hgrid file in gr3 format """
        print("Reading hgrid.gr3 file")
        
    def plot(self):
        """ Plot the hgrid.gr3 mesh """
