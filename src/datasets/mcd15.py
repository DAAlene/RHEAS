""" RHEAS module for retrieving MODIS Leaf Area Index data (MCD15 product).

.. module:: mcd15
   :synopsis: Retrieve MODIS LAI data

.. moduleauthor:: Kostas Andreadis <kandread@jpl.nasa.gov>

"""

import modis
import tempfile
import dbio
from lxml import html
import re
import subprocess
import glob
import shutil
import datasets
from datetime import timedelta
import requests
import logging


table = "lai.modis"
username = "rheas"
password = "nasaRhea5"


def dates(dbname):
    dts = datasets.dates(dbname, table)
    return dts


def download(dbname, dts, bbox):
    """Downloads the combined MODIS LAI data product MCD15 for
    a specific date *dt* and imports them into the PostGIS database *dbname*."""
    log = logging.getLogger(__name__)
    res = 0.01
    burl = "http://e4ftl01.cr.usgs.gov/MOTA/MCD15A2.005"
    tiles = modis.findTiles(bbox)
    if tiles is not None:
        for dt in [dts[0] + timedelta(dti) for dti in range((dts[-1] - dts[0]).days + 1)]:
            outpath = tempfile.mkdtemp()
            url = "{0}/{1:04d}.{2:02d}.{3:02d}".format(
                burl, dt.year, dt.month, dt.day)
            req = requests.get(url, auth=(username, password))
            if req.status_code == 200:
                dom = html.fromstring(req.text)
                files = [link for link in dom.xpath('//a/@href')]
                if len(files) > 0:
                    filenames = [filter(lambda s: re.findall(r'MCD.*h{0:02d}v{1:02d}.*hdf$'.format(t[1], t[0]), s), files) for t in tiles]
                    for filename in filenames:
                        if len(filename) > 0:
                            filename = filename[0]
                            proc = subprocess.Popen(["wget", "-L", "--load-cookies", ".cookiefile", "--save-cookies", ".cookiefile", "--user", username, "--password", password, "{0}/{1}".format(url, filename), "-O", "{0}/{1}".format(outpath, filename)], stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
                            out, err = proc.communicate()
                            log.debug(out)
                            proc = subprocess.Popen(["gdal_translate", "HDF4_EOS:EOS_GRID:{0}/{1}:MOD_Grid_MOD15A2:Lai_1km".format(
                                outpath, filename), "{0}/{1}".format(outpath, filename).replace("hdf", "tif")], stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
                            out, err = proc.communicate()
                            log.debug(out)
                    tifs = glob.glob("{0}/*.tif".format(outpath))
                    if len(tifs) > 0:
                        proc = subprocess.Popen(["gdal_merge.py", "-o", "{0}/lai.tif".format(outpath)] + tifs, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
                        out, err = proc.communicate()
                        log.debug(out)
                        proc = subprocess.Popen(["gdal_calc.py", "-A", "{0}/lai.tif".format(outpath), "--outfile={0}/lai1.tif".format(outpath), "--NoDataValue=-9999", "--calc=(A<101.0)*(0.1*A+9999.0)-9999.0"], stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
                        out, err = proc.communicate()
                        log.debug(out)
                        proc = subprocess.Popen(["gdalwarp", "-t_srs", "+proj=latlong +ellps=sphere", "-tr", str(res), str(-res), "{0}/lai1.tif".format(outpath), "{0}/lai2.tif".format(outpath)], stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
                        out, err = proc.communicate()
                        log.debug(out)
                        proc = subprocess.Popen(["gdal_translate", "-a_srs", "epsg:4326", "{0}/lai2.tif".format(outpath), "{0}/lai3.tif".format(outpath)], stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
                        out, err = proc.communicate()
                        log.debug(out)
                        dbio.ingest(
                            dbname, "{0}/lai3.tif".format(outpath), dt, table, False)
                    shutil.rmtree(outpath)
            else:
                log.warning("MCD15 data not available for {0}. Skipping download!".format(
                    dt.strftime("%Y-%m-%d")))
