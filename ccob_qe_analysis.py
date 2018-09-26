import os
import glob
import lsst.eotest.image_utils as imutils
import lsst.eotest.sensor as sensorTest
import lsst.eotest.raft as raft
import matplotlib.pyplot as plt
import numpy as np
import yaml
import sys
import ccob_utils as u
import ccob_beam as b
import pickle

class CcobQE: 
    
    def __init__(self, config_file_beam, config_file_data):
        self.config_file_beam = config_file_beam
        self.config_file_data = config_file_data
 

    def make_ccob_beam(self, led_name='red', ref_amp=13, ref_slot='11', ref_pix_x=1000,ref_pix_y=256):
        """
        Make a CCOB beam object for a scan
        """
        config = u.load_ccob_config(self.config_file_beam)
        self.led = led_name
        config['led_name'] = self.led
        self.beam = b.CcobBeam(config)
        self.beam.recons(ref_slot=ref_slot, ref_amp=ref_amp, ref_pix_x=ref_pix_x,ref_pix_y=ref_pix_y)
        self.beam.make_image()
        self.beam.find_max()
        
        filename = self.beam.config['led_name']+'_beam_slot'+self.beam.properties['ref_slot']+\
        '_amp'+str(self.beam.properties['ref_amp'])+'_refx'+str(self.beam.properties['ref_pix_x'])+\
        '_refy'+str(self.beam.properties['ref_pix_y'])+'.pkl'
        print('Printing to ',filename)
        self.beam.save(os.path.join(beam.config['tmp_dir'],filename))
        return self.beam

    def load_ccob_beam(self, infile):
        """
        Load an existing CCOB beam object, that would have been previously
        generate using make_ccob_beam
        """
        self.beam = pickle.load(open(infile,'rb'))
    

    def load_ccd(self):
        """
        Load and generate mosaic image from a given sensor illuminated 
        by the CCOB
        """

        #config_file_data = '../ccob_config_RTM-006.yaml'
        config_data = u.load_ccob_config(self.config_file_data)
        config_beam = u.load_ccob_config(self.config_file_beam)

        slot = self.beam.properties['ref_slot']
        file_list=sorted(u.find_files(config_data, slot=slot))

        mean_slot_file = slot+'_mean_ccob_image.fits'
        imutils.fits_mean_file(file_list, os.path.join(config_data['tmp_dir'],mean_slot_file))

        fits_file = os.path.join(config_data['tmp_dir'],mean_slot_file)
        gains_dict={}
        ccd_dict={}

        #bias_frames = glob.glob(os.path.join(config['path'], slot+'_bias*'))
        mean_bias_file = slot+'_mean_bias_image_RTM-006_new.fits'
        #imutils.fits_mean_file(bias_frames, os.path.join(config['tmp_dir'],mean_bias_file))
        ccd_dict = sensorTest.MaskedCCD(fits_file, bias_frame=os.path.join(config_data['tmp_dir'],mean_bias_file))
        eotest_results_file = os.path.join(config_data['eo_data_path'],\
                                           '{}_eotest_results.fits'.format(ccd_dict.md('LSST_NUM')))

        gains_dict = u.gains(eotest_results_file)
        self.ccd = {}
        self.ccd['mosaic'], self.ccd['amp_coord'] = u.make_ccd_2d_array(fits_file, gains=gains_dict)
        self.ccd['xpos_ccob'] = config_data['xpos']
        self.ccd['ypos_ccob'] = config_data['ypos']
        
        return self.ccd

    def compute_QE(self):

        # First need to match a beam image to the ccd data, given the position of the CCOB
        ref_pix = u.pix_coord_in_mosaic(self.ccd['amp_coord'], self.beam.properties['ref_amp'], \
                                        self.beam.properties['ref_pix_y'],
                                        self.beam.properties['ref_pix_x'])

        delta_x = float(self.ccd['ypos_ccob']) - self.beam.properties['max_yccob']
        delta_y = float(self.ccd['xpos_ccob']) - self.beam.properties['max_xccob']
        delta_x_pix = int(delta_x/0.01)
        delta_y_pix = int(delta_y/0.01)

        print('deplacement in mm: dx=%0.2f dy=%0.2f'%(delta_x, delta_y))
        print('deplacement in pixels: dx=%i dy=%i'%(delta_x_pix, delta_y_pix))

        geom_center_pos=(ref_pix[0]+delta_x_pix, ref_pix[1]+delta_y_pix)

        # distance from beam center to ccd edges in mm
        dist_to_left = geom_center_pos[0]*0.01
        dist_to_bottom = geom_center_pos[1]*0.01
        dist_to_right = (self.ccd['mosaic'].shape[1]-geom_center_pos[0])*0.01
        dist_to_top = (self.ccd['mosaic'].shape[0]-geom_center_pos[1])*0.01

        # bounding box to use to reconstruct the CCOB with dimensions matching ccd
        bbox = (self.beam.properties['max_xccob'] - dist_to_left,
        self.beam.properties['max_xccob'] + dist_to_right,
        self.beam.properties['max_yccob'] - dist_to_bottom,
        self.beam.properties['max_yccob'] + dist_to_top)

        xarr = np.linspace(bbox[0],bbox[1],self.ccd['mosaic'].shape[1])
        yarr = np.linspace(bbox[2],bbox[3],self.ccd['mosaic'].shape[0])
        self.beam_image = self.beam.beam_image['f_interp'](xarr, yarr)

        # Raw QE (flat) is simply the ccd-to-beam ratio
        self.QE = self.ccd['mosaic']/self.beam_image
        return self.QE


    def make_fits(self, outfile):
        """
        Save the mosaicked QE image into a fits file, using the default format 
        """
        return 0