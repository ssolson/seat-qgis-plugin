import sys
import os
import unittest
import numpy as np
import pandas as pd
from osgeo import gdal
from unittest.mock import patch, MagicMock

# Get the directory in which the current script is located
script_dir = os.path.dirname(os.path.realpath(__file__))

# Import seat
parent_dir = os.path.dirname(script_dir)
sys.path.insert(0, parent_dir)

# fmt: off
from seat.modules import stressor_utils as su

# fmt: on
# from seat.stressor_utils import estimate_grid_spacing

class TestEstimateGridSpacing(unittest.TestCase):

    def test_evenly_spaced_points(self):
        # Evenly spaced points
        x, y = np.meshgrid(np.arange(0, 10, 1), np.arange(0, 10, 1))
        x = x.flatten()
        y = y.flatten()
        expected_spacing = 1

        spacing = su.estimate_grid_spacing(x, y)
        self.assertAlmostEqual(spacing, expected_spacing, delta=0.1)

    def test_randomly_distributed_points(self):
        # Randomly distributed points
        np.random.seed(0)  # for reproducible results
        x = np.random.rand(100)
        y = np.random.rand(100)
        # Hardcoded expected spacing
        expected_spacing = 0.038

        spacing = su.estimate_grid_spacing(x, y)
        self.assertAlmostEqual(spacing, expected_spacing, delta=0.02)


class TestCreateStructuredArrayFromUnstructured(unittest.TestCase):

    def test_structured_array_creation(self):
        # Example unstructured data (could be synthetic or based on a simple pattern)
        x = np.array([0, 1, 1])
        y = np.array([0, 0, 1])
        z = np.array([10, 20, 30])
        dxdy = 1

        refxg, refyg, z_interp = su.create_structured_array_from_unstructured(x, y, z, dxdy)

        # Assert the shapes of the returned arrays
        self.assertEqual(refxg.shape, refyg.shape)
        self.assertEqual(refxg.shape, z_interp.shape)

        # Assert the range and spacing of the grid
        np.testing.assert_array_almost_equal(refxg[0, :], np.arange(0, 2, dxdy))
        np.testing.assert_array_almost_equal(refyg[:, 0], np.arange(0, 2, dxdy))


class TestRedefineStructuredGrid(unittest.TestCase):

    def test_redefined_grid(self):
        # Example structured data
        x = np.linspace(0, 10, 5)
        y = np.linspace(0, 10, 5)
        xx, yy = np.meshgrid(x, y)
        z = np.sin(xx) * np.cos(yy)
        
        x_new, y_new, z_new = su.redefine_structured_grid(xx, yy, z)

        # Assert the shapes of the returned arrays
        self.assertEqual(x_new.shape, y_new.shape)
        self.assertEqual(x_new.shape, z_new.shape)

        # Assert the range and spacing of the grid
        dx = np.nanmin(np.diff(x_new[0, :]))
        np.testing.assert_almost_equal(x_new[0, 1] - x_new[0, 0], dx)
        np.testing.assert_almost_equal(y_new[1, 0] - y_new[0, 0], dx)


class TestResampleStructuredGrid(unittest.TestCase):

    def test_grid_resampling(self):
        # Input grid
        x = np.linspace(0, 10, 5)
        y = np.linspace(0, 10, 5)
        x_grid, y_grid = np.meshgrid(x, y)
        z = np.sin(x_grid) * np.cos(y_grid)

        # Output grid
        X_grid_out = np.linspace(0, 10, 10)
        Y_grid_out = np.linspace(0, 10, 10)
        X_grid_out, Y_grid_out = np.meshgrid(X_grid_out, Y_grid_out)

        # Resample
        z_resampled = su.resample_structured_grid(x_grid, y_grid, z, X_grid_out, Y_grid_out, interpmethod='nearest')

        # Assert the shape of the resampled grid
        self.assertEqual(z_resampled.shape, X_grid_out.shape)


class TestCalcReceptorArray(unittest.TestCase):

    def setUp(self):
        # Setup any common data used across tests
        self.x = np.array([1, 2, 3])
        self.y = np.array([1, 2, 3])

    @patch('seat.modules.stressor_utils.gdal.Open')
    @patch('seat.modules.stressor_utils.griddata', return_value=np.array([0, 1, 2]))
    def test_with_tif_file(self, mock_griddata, mock_gdal_open):
        # Configure the mock for gdal.Open to simulate a .tif file read
        mock_dataset = MagicMock()
        mock_band = MagicMock()
        mock_band.ReadAsArray.return_value = np.array([0, 1, 2])
        mock_dataset.GetRasterBand.return_value = mock_band
        mock_dataset.GetGeoTransform.return_value = (0, 1, 0, 0, 0, -1)
        mock_dataset.RasterXSize = 3
        mock_dataset.RasterYSize = 3
        mock_gdal_open.return_value = mock_dataset

        receptor_filename = 'test.tif'
        receptor_array = su.calc_receptor_array(receptor_filename, self.x, self.y)

        # Assert the output
        np.testing.assert_array_equal(receptor_array, np.array([0, 1, 2]))
        mock_gdal_open.assert_called_once_with(receptor_filename)
        mock_griddata.assert_called_once()

    @patch('seat.modules.stressor_utils.pd.read_csv')
    def test_with_csv_file(self, mock_read_csv):
        # Mock the behavior of pd.read_csv for a .csv file
        mock_read_csv.return_value = pd.DataFrame(data=[[1]])
        receptor_filename = 'test.csv'
        receptor_array = su.calc_receptor_array(receptor_filename, self.x, self.y)

        # Assert the output
        np.testing.assert_array_equal(receptor_array, np.ones(self.x.shape))
        mock_read_csv.assert_called_once_with(receptor_filename, header=None, index_col=0)

    def test_without_file(self):
        receptor_filename = ''
        receptor_array = su.calc_receptor_array(receptor_filename, self.x, self.y)

        # Assert the output
        expected_array = 200e-6 * np.ones(self.x.shape)
        np.testing.assert_array_almost_equal(receptor_array, expected_array,  decimal=6)

    def test_invalid_file_type(self):
        receptor_filename = 'test.invalid'
        with self.assertRaises(Exception) as context:
            su.calc_receptor_array(receptor_filename, self.x, self.y)
        
        self.assertTrue(f"Invalid Receptor File {receptor_filename}. Must be of type .tif or .csv" in str(context.exception))


class TestTrimZeros(unittest.TestCase):

    def test_trim_zeros(self):
        # Create test data with zeros on edges
        x = np.zeros((5, 5))
        y = np.zeros((5, 5))
        z1 = np.zeros((1, 1, 5, 5))
        z2 = np.zeros((1, 1, 5, 5))
        x[1:-1, 1:-1] = 1
        y[1:-1, 1:-1] = 1
        z1[:, :, 1:-1, 1:-1] = 1
        z2[:, :, 1:-1, 1:-1] = 1

        x_trimmed, y_trimmed, z1_trimmed, z2_trimmed = su.trim_zeros(x, y, z1, z2)

        # Assert the shapes of the returned arrays
        self.assertEqual(x_trimmed.shape, (3, 3))
        self.assertEqual(y_trimmed.shape, (3, 3))
        self.assertEqual(z1_trimmed.shape, (1, 1, 3, 3))
        self.assertEqual(z2_trimmed.shape, (1, 1, 3, 3))

        # Assert that the arrays are trimmed correctly (no zeros)
        self.assertTrue(np.all(x_trimmed != 0))
        self.assertTrue(np.all(y_trimmed != 0))
        self.assertTrue(np.all(z1_trimmed != 0))
        self.assertTrue(np.all(z2_trimmed != 0))


class TestCreateRaster(unittest.TestCase):

    @patch('seat.modules.stressor_utils.gdal.GetDriverByName')
    def test_create_raster(self, mock_get_driver_by_name):
        # Mock the GDAL driver and its Create method
        mock_driver = MagicMock()
        mock_create = MagicMock()
        mock_driver.Create = mock_create
        mock_get_driver_by_name.return_value = mock_driver

        # Call the function
        output_path = 'test_output.tif'
        cols = 100
        rows = 100
        nbands = 1
        eType = gdal.GDT_Float32

        raster = su.create_raster(output_path, cols, rows, nbands, eType)

        # Assert that GetDriverByName and Create were called correctly
        mock_get_driver_by_name.assert_called_once_with("GTiff")
        mock_create.assert_called_once_with(output_path, cols, rows, nbands, eType=gdal.GDT_Float32)

        # Assert that the function returns a mock raster object
        self.assertEqual(raster, mock_create.return_value)


class TestNumpyArrayToRaster(unittest.TestCase):

    @patch('seat.modules.stressor_utils.os.path.exists')
    @patch('seat.modules.stressor_utils.gdal')
    @patch('seat.modules.stressor_utils.osr.SpatialReference')
    def test_numpy_array_to_raster(self, mock_spatial_reference, mock_gdal, mock_os_path_exists):
        # Mock the behavior of GDAL and os.path.exists
        mock_os_path_exists.return_value = True
        mock_output_raster = MagicMock()
        mock_band = MagicMock()
        mock_output_raster.GetRasterBand.return_value = mock_band
        mock_spatial_ref_instance = mock_spatial_reference.return_value
        mock_spatial_ref_instance.ExportToWkt.return_value = 'WKT'

        # Test data
        numpy_array = np.array([[1, 2], [3, 4]])
        bounds = [0, 0]
        cell_resolution = [1, 1]
        spatial_reference_system_wkid = 4326
        output_path = 'test_output.tif'

        result_path = su.numpy_array_to_raster(mock_output_raster, numpy_array, bounds, cell_resolution, spatial_reference_system_wkid, output_path)

        # Asserts
        mock_output_raster.SetProjection.assert_called_once()
        mock_output_raster.SetGeoTransform.assert_called_once()
        mock_band.WriteArray.assert_called_once_with(numpy_array)
        mock_band.FlushCache.assert_called_once()
        mock_band.ComputeStatistics.assert_called_once_with(False)
        self.assertEqual(result_path, output_path)


class TestFindUtmSrid(unittest.TestCase):

    def test_northern_hemisphere(self):
        lon = 10  # Longitude in the Northern Hemisphere
        lat = 50  # Latitude in the Northern Hemisphere
        srid = 4326
        expected_srid = 32600 + np.floor((lon + 186) / 6)
        self.assertEqual(su.find_utm_srid(lon, lat, srid), expected_srid)

    def test_southern_hemisphere(self):
        lon = 30  # Longitude in the Southern Hemisphere
        lat = -30  # Latitude in the Southern Hemisphere
        srid = 4326
        expected_srid = 32700 + np.floor((lon + 186) / 6)
        self.assertEqual(su.find_utm_srid(lon, lat, srid), expected_srid)

    def test_on_equator(self):
        lon = 0  # On the Prime Meridian
        lat = 0  # On the Equator
        srid = 4326
        expected_srid = 32600 + np.floor((lon + 186) / 6)
        self.assertEqual(su.find_utm_srid(lon, lat, srid), expected_srid)

    def test_wrong_srid(self):
        lon = 10
        lat = 10
        srid = 1234  # Incorrect SRID
        with self.assertRaises(AssertionError):
            su.find_utm_srid(lon, lat, srid)


class TestReadRaster(unittest.TestCase):

    @patch('seat.modules.stressor_utils.gdal.Open')
    def test_read_raster(self, mock_gdal_open):
        # Mock data setup
        raster_name = 'path/to/raster.tif'

        # Create a mock object to simulate gdal.Dataset
        mock_dataset = MagicMock()
        mock_band = MagicMock()
        # Simulate raster array returned by ReadAsArray
        mock_raster_array = np.array([[1, 2], [3, 4]])
        mock_band.ReadAsArray.return_value = mock_raster_array
        mock_dataset.GetRasterBand.return_value = mock_band
        # Simulate GetGeoTransform return value
        mock_geo_transform = (0, 1, 0, 0, 0, -1)
        mock_dataset.GetGeoTransform.return_value = mock_geo_transform
        # Simulate raster size
        mock_dataset.RasterXSize = 2
        mock_dataset.RasterYSize = 2

        mock_gdal_open.return_value = mock_dataset

        # Call the function under test
        rx, ry, raster_array = su.read_raster(raster_name)

        # Expected values
        expected_rx = np.array([[0.5, 1.5], [0.5, 1.5]])
        expected_ry = np.array([[-0.5, -0.5], [-1.5, -1.5]])
        expected_raster_array = np.array([[1, 2], [3, 4]])

        # Asserts
        np.testing.assert_array_equal(rx, expected_rx)
        np.testing.assert_array_equal(ry, expected_ry)
        np.testing.assert_array_equal(raster_array, expected_raster_array)

        # Verify that gdal.Open was called with the correct raster name
        mock_gdal_open.assert_called_once_with(raster_name)


class TestSecondaryConstraintGeotiffToNumpy(unittest.TestCase):

    @patch('seat.modules.stressor_utils.gdal.Open')
    @patch('seat.modules.stressor_utils.osr.SpatialReference')
    def test_secondary_constraint_geotiff_to_numpy(self, mock_spatial_reference, mock_gdal_open):
        # Mock setup for gdal.Open
        raster_name = 'path/to/constraint.tif'
        mock_dataset = MagicMock()
        mock_band = MagicMock()
        # Simulate raster array returned by ReadAsArray
        mock_raster_array = np.array([[1, 2], [3, 4]])
        mock_band.ReadAsArray.return_value = mock_raster_array
        mock_dataset.GetRasterBand.return_value = mock_band
        # Simulate GetGeoTransform return value
        mock_geo_transform = (0, 1, 0, 0, 0, -1)
        mock_dataset.GetGeoTransform.return_value = mock_geo_transform
        # Simulate raster size and projection
        mock_dataset.RasterXSize = 2
        mock_dataset.RasterYSize = 2
        mock_dataset.GetProjection.return_value = 'PROJECTION_WKT_HERE'
        mock_gdal_open.return_value = mock_dataset

        # Mock setup for osr.SpatialReference
        mock_spatial_ref_instance = MagicMock()
        mock_srs_attr_value = '4326'
        mock_spatial_ref_instance.GetAttrValue.return_value = mock_srs_attr_value
        mock_spatial_reference.return_value = mock_spatial_ref_instance

        # Expected values
        expected_x_grid = np.array([[0.5, 1.5], [0.5, 1.5]])
        expected_y_grid = np.array([[-0.5, -0.5], [-1.5, -1.5]])
        expected_array = np.array([[1, 2], [3, 4]])

        # Call the function under test
        x_grid, y_grid, array = su.secondary_constraint_geotiff_to_numpy(raster_name)

        # Asserts
        np.testing.assert_array_equal(x_grid, expected_x_grid)
        np.testing.assert_array_equal(y_grid, expected_y_grid)
        np.testing.assert_array_equal(array, expected_array)

        # Verify osr.SpatialReference was called with the projection WKT
        mock_spatial_reference.assert_called_once_with(wkt='PROJECTION_WKT_HERE')
        # Verify GetAttrValue was called to check for EPSG:4326
        mock_spatial_ref_instance.GetAttrValue.assert_called_with('AUTHORITY', 1)


class TestCalculateCellArea(unittest.TestCase):

    def test_latlon_true(self):
        # Test data for a lat/lon grid
        rx = np.array([[0, 1], [0, 1]])
        ry = np.array([[0, 0], [1, 1]])
        rxm, rym, square_area = su.calculate_cell_area(rx, ry, latlon=True)

        # Assert the area calculation
        expected_area = np.array([[1.230722e+10]])
        np.testing.assert_array_almost_equal(square_area, expected_area, decimal=-4)

        # Assert rxm and rym values
        expected_rxm = np.array([[0.5]])
        expected_rym = np.array([[0.5]])
        np.testing.assert_array_almost_equal(rxm, expected_rxm)
        np.testing.assert_array_almost_equal(rym, expected_rym)

    def test_latlon_false(self):
        # Test data for a planar grid
        rx = np.array([[0, 1], [0, 1]])
        ry = np.array([[0, 0], [1, 1]])
        rxm, rym, square_area = su.calculate_cell_area(rx, ry, latlon=False)

        # Assert the area calculation
        expected_area = np.array([[1]])
        np.testing.assert_array_equal(square_area, expected_area)

        # Assert rxm and rym values
        expected_rxm = np.array([[0.5]])
        expected_rym = np.array([[0.5]])
        np.testing.assert_array_equal(rxm, expected_rxm)
        np.testing.assert_array_equal(rym, expected_rym)


class TestBinData(unittest.TestCase):

    def test_bin_data(self):
        # Sample input data
        zm = np.array([1, 2, 3, 4, 5, 6, 7, 8, 9, 10])
        square_area = np.ones(zm.shape)  # Assume each cell has an area of 1 for simplicity
        nbins = 5

        # Expected output
        expected_bins = {'bin start': np.array([1., 2.8, 4.6, 6.4, 8.2]),
                        'bin end': np.array([2.8, 4.6, 6.4, 8.2, 10.]),
                        'bin center': np.array([1.9, 3.7, 5.5, 7.3, 9.1]),
                        'count': np.array([2, 2, 2, 2, 2]),
                        'Area': np.array([2., 2., 2., 2., 2.])}

        # Call the function
        result = su.bin_data(zm, square_area, nbins)

        # Assert the results
        np.testing.assert_array_almost_equal(result['bin start'], expected_bins['bin start'])
        np.testing.assert_array_almost_equal(result['bin end'], expected_bins['bin end'])
        np.testing.assert_array_almost_equal(result['bin center'], expected_bins['bin center'])
        np.testing.assert_array_equal(result['count'], expected_bins['count'])
        np.testing.assert_array_equal(result['Area'], expected_bins['Area'])

    def test_bin_data_with_varying_area(self):
        # Sample input data with varying area
        zm = np.array([1, 2, 3, 4, 5, 6, 7, 8, 9, 10])
        square_area = np.array([1, 1, 2, 2, 3, 3, 4, 4, 5, 5])  # Varying area for each cell
        nbins = 5

        # Expected output with consideration for varying area
        expected_bins = {'bin start': np.array([1., 2.8, 4.6, 6.4, 8.2]),
                        'bin end': np.array([2.8, 4.6, 6.4, 8.2, 10.]),
                        'bin center': np.array([1.9, 3.7, 5.5, 7.3, 9.1]),
                        'count': np.array([2, 2, 2, 2, 2]),
                        'Area': np.array([2., 4., 6., 8., 10.])}  # Area now reflects the input square_area

        # Call the function
        result = su.bin_data(zm, square_area, nbins)

        # Assert the results with varying area
        np.testing.assert_array_almost_equal(result['bin start'], expected_bins['bin start'])
        np.testing.assert_array_almost_equal(result['bin end'], expected_bins['bin end'])
        np.testing.assert_array_almost_equal(result['bin center'], expected_bins['bin center'])
        np.testing.assert_array_equal(result['count'], expected_bins['count'])
        np.testing.assert_array_equal(result['Area'], expected_bins['Area'])


class TestBinReceptor(unittest.TestCase):

    def setUp(self):
        # Set up sample data for tests
        self.zm = np.array([1, 2, 3, 4, 5, 6, 7, 8, 9, 10])
        self.receptor = np.array([0, 0, 1, 1, 2, 2, 3, 3, 4, 4])
        self.square_area = np.array([1, 1, 2, 2, 3, 3, 4, 4, 5, 5])  # Varying area for each cell
        self.nbins = 5
        self.receptor_names = ['Type A', 'Type B', 'Type C', 'Type D', 'Type E']

    def test_bin_receptor_without_names(self):
        # Test without passing receptor_names
        result = su.bin_receptor(self.zm, self.receptor, self.square_area, self.nbins)

        # Verifying that keys for each unique receptor value are present
        for rval in np.unique(self.receptor):
            self.assertIn(f'Area, receptor value {rval}', result)


    def test_bin_receptor_with_names(self):
        # Test with passing receptor_names
        result = su.bin_receptor(self.zm, self.receptor, self.square_area, self.nbins, self.receptor_names)

        # Verifying that the receptor names are used in the keys
        for name in self.receptor_names:
            self.assertIn(name, result)


    def test_bin_receptor_calculation(self):
        # Test comprehensive functionality including bin statistics and area percentage calculations
        result = su.bin_receptor(self.zm, self.receptor, self.square_area, self.nbins)

        # Expected bin statistics
        expected_result = {
            'bin start': np.array([1. , 2.8, 4.6, 6.4, 8.2]), 
            'bin end': np.array([ 2.8,  4.6,  6.4,  8.2, 10. ]), 
            'bin center': np.array([1.9, 3.7, 5.5, 7.3, 9.1]), 
            'Area, receptor value 0':np. array([2., 0., 0., 0., 0.]), 
            'Area percent, receptor value 0': np.array([100.,   0.,   0.,   0.,   0.]), 
            'Area, receptor value 1': np.array([0., 4., 0., 0., 0.]),
            'Area percent, receptor value 1': np.array([  0., 100.,   0.,   0.,   0.]), 
            'Area, receptor value 2': np.array([0., 0., 6., 0., 0.]), 
            'Area percent, receptor value 2': np.array([  0.,   0., 100.,   0.,   0.]), 
            'Area, receptor value 3': np.array([0., 0., 0., 8., 0.]), 
            'Area percent, receptor value 3': np.array([  0.,   0.,   0., 100.,   0.]), 
            'Area, receptor value 4': np.array([ 0.,  0.,  0.,  0., 10.]), 
            'Area percent, receptor value 4': np.array([  0.,   0.,   0.,   0., 100.])
        }

        # Verify bin statistics
        np.testing.assert_array_almost_equal(result['bin start'], expected_result['bin start'])
        np.testing.assert_array_almost_equal(result['bin end'], expected_result['bin end'])
        np.testing.assert_array_almost_equal(result['bin center'], expected_result['bin center'])

        # Directly verify area and area percent for each receptor value based on actual outputs
        for rval in np.unique(self.receptor):
            area_key = f'Area, receptor value {rval}'
            area_percent_key = f'Area percent, receptor value {rval}'
      
            # Assert area and area percentages based on provided actual result
            np.testing.assert_array_almost_equal(result[area_key], expected_result[area_key])
            np.testing.assert_array_almost_equal(result[area_percent_key], expected_result[area_percent_key])


class TestBinLayer(unittest.TestCase):
    # TODO: Check correctness of values. 
    #   Currently only checking if the function calls are made correctly
    def setUp(self):
        # Mock data setup
        self.raster_filename = "path/to/raster.tif"
        self.receptor_filename = "path/to/receptor.tif"

        # Example raster data
        self.rx = np.arange(0, 10)
        self.ry = np.arange(0, 10)
        self.z = np.random.rand(10, 10) * 100  # Example raster values
        self.receptor = np.random.randint(0, 5, (10, 10))  # Example receptor values

    @patch('seat.modules.stressor_utils.read_raster')
    @patch('seat.modules.stressor_utils.calculate_cell_area')
    @patch('seat.modules.stressor_utils.resample_structured_grid')
    @patch('pandas.DataFrame')
    def test_bin_layer_without_receptor(self, mock_df, mock_resample, mock_calc_area, mock_read_raster):
        # Mock the function calls inside bin_layer
        mock_read_raster.return_value = (self.rx, self.ry, self.z)
        mock_calc_area.return_value = (self.rx, self.ry, np.ones_like(self.z))  # Simplified square area
        mock_resample.side_effect = lambda rx, ry, z, rxm, rym, **kwargs: z  # Simplified resample to return z directly

        # Call the function under test
        su.bin_layer(self.raster_filename)

        # Check that read_raster was called with the raster_filename
        mock_read_raster.assert_called_once_with(self.raster_filename)


    @patch('seat.modules.stressor_utils.read_raster')
    @patch('seat.modules.stressor_utils.calculate_cell_area')
    @patch('seat.modules.stressor_utils.resample_structured_grid')
    @patch('pandas.DataFrame')
    def test_bin_layer_with_receptor(self, mock_df, mock_resample, mock_calc_area, mock_read_raster):
        # Mock setup for both raster and receptor
        mock_read_raster.side_effect = [(self.rx, self.ry, self.z), (self.rx, self.ry, self.receptor)]
        mock_calc_area.return_value = (self.rx, self.ry, np.ones_like(self.z))  # Simplified square area
        mock_resample.side_effect = lambda rx, ry, z, rxm, rym, **kwargs: z  # Simplified resample to return z directly

        # Call the function under test
        su.bin_layer(self.raster_filename, self.receptor_filename)

        # Check that read_raster was called correctly for both raster and receptor
        calls = [unittest.mock.call(self.raster_filename), unittest.mock.call(self.receptor_filename)]
        mock_read_raster.assert_has_calls(calls, any_order=True)


class TestClassifyLayerArea(unittest.TestCase):
    # TODO: Check correctness of values. 
    @patch('seat.modules.stressor_utils.read_raster')
    @patch('seat.modules.stressor_utils.calculate_cell_area')
    @patch('seat.modules.stressor_utils.resample_structured_grid')
    @patch('pandas.DataFrame')
    def test_classify_layer_area_without_receptor(self, mock_df, mock_resample, mock_calc_area, mock_read_raster):
        # Mock data and function return values
        raster_filename = "path/to/raster.tif"
        rx, ry = np.meshgrid(np.arange(5), np.arange(5))
        z = np.array([[1, 2, 1, 2, 3], [2, 1, 3, 1, 2], [1, 2, 1, 2, 3], [2, 1, 3, 1, 2], [1, 2, 1, 2, 3]])
        square_area = np.ones(z.shape).flatten()  # Assume each cell has an area of 1 for simplicity

        mock_read_raster.return_value = (rx, ry, z)
        mock_calc_area.return_value = (rx, ry, square_area)
        mock_resample.side_effect = lambda rx, ry, z, rxm, rym, **kwargs: z.flatten()

        # Call the function under test
        su.classify_layer_area(raster_filename, at_values=[1, 2, 3], value_names=['One', 'Two', 'Three'])

        # Assertions to check if the function behaved as expected
        mock_read_raster.assert_called_once_with(raster_filename)
        mock_calc_area.assert_called_once()
        mock_resample.assert_called()


class TestClassifyLayerArea2ndConstraint(unittest.TestCase):
    # TODO: Check correctness of values.     
    @patch('seat.modules.stressor_utils.read_raster')
    @patch('seat.modules.stressor_utils.calculate_cell_area')
    @patch('seat.modules.stressor_utils.resample_structured_grid')
    # Add more decorators as needed to mock dependencies
    def test_classify_layer_area_2nd_constraint(self, mock_resample, mock_calc_area, mock_read_raster):
        # Mock setup for reading the raster and secondary constraint
        raster_filename = "path/to/primary_raster.tif"
        secondary_constraint_filename = "path/to/secondary_constraint.tif"
        
        # Example mock return values (simplified)
        rx, ry = np.meshgrid(np.arange(5), np.arange(5))  # Example coordinates
        primary_raster_z = np.random.rand(5, 5) * 100  # Example primary raster values
        secondary_raster_z = np.random.randint(0, 2, (5, 5))  # Example binary constraint raster
        square_area = np.ones(primary_raster_z.shape).flatten()  # Simplified square area

        mock_read_raster.side_effect = [(rx, ry, primary_raster_z), (rx, ry, secondary_raster_z)]
        mock_calc_area.return_value = (rx, ry, square_area)
        mock_resample.side_effect = lambda rx, ry, z, rxm, rym, **kwargs: z.flatten()
        
        at_raster_values = [10, 20, 30]  # Example value thresholds
        at_raster_value_names = ['Low', 'Medium', 'High']  # Corresponding names
        limit_constraint_range = (0, 1)  # Example constraint range
        latlon = True  # Assuming geographic coordinates

        # Call the function under test
        result = su.classify_layer_area_2nd_Constraint(
            raster_filename,
            secondary_constraint_filename,
            at_raster_values,
            at_raster_value_names,
            limit_constraint_range,
            latlon
        )
        
        self.assertIsInstance(result, pd.DataFrame)


if __name__ == '__main__':
    unittest.main()
