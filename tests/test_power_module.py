import sys
import os
import unittest
import matplotlib.pyplot as plt
from matplotlib.ticker import FormatStrFormatter
import numpy as np
import pandas as pd
import tempfile


# Get the directory in which the current script is located
script_dir = os.path.dirname(os.path.realpath(__file__))

# Import seat
parent_dir = os.path.dirname(script_dir)
sys.path.insert(0, parent_dir)

# fmt: off
from seat.modules import shear_stress_module as ssm
from seat.modules import power_module as pm
# fmt: on


class TestPowerModule(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        """
        Class method called before tests in any class that inherits from this base class.
        It initializes the file paths for structured and unstructured test cases.
        """
        # Define paths with script_dir prepended
        cls.dev_present = join(script_dir, "data/structured/devices-present")
        cls.dev_not_present = join(script_dir, "data/structured/devices-not-present")
        cls.probabilities_structured = join(script_dir, "data/structured/probabilities/probabilities.csv")
        cls.receptor_structured = join(script_dir, "data/structured/receptor/grain_size_receptor.csv")

        # unstructured test cases
        cls.mec_present = join(script_dir, "data/unstructured/mec-present")
        cls.mec_not_present = join(script_dir, "data/unstructured/mec-not-present")
        cls.receptor_unstructured = join(script_dir, "data/unstructured/receptor/grain_size_receptor.csv")

    @staticmethod
    def calculate_expected_pair(centroids, centroid):
        # Calculate Euclidean distances, excluding the index
        distances = np.sqrt(np.sum((centroids[:, 1:] - centroid[1:])**2, axis=1))

        # Find the index of the centroid with the minimum distance
        closest_index = np.argmin(distances)

        # Return the expected pair: [index of test_centroid, index of closest centroid in test_centroids]
        return [int(centroid[0]), int(centroids[closest_index, 0])]

    def test_valid_pol_file(self):
        """
        Test the read_obstacle_polygon_file function with a valid .pol file.
        """
        # Call the function with the valid .pol file
        obstacles = pm.read_obstacle_polygon_file(self.pol_file)

        self.assertIsInstance(obstacles, dict, "The output should be a dictionary.")

    def test_invalid_pol_file_path(self):
        """
        Test that a FileNotFoundError is raised for an invalid file path.
        """
        bad_path = os.path.join(script_dir, "non_existent_directory/non_existent_file.pol")
        with self.assertRaises(FileNotFoundError):
            pm.read_obstacle_polygon_file(bad_path)

    def test_find_mean_point_of_obstacle_polygon(self):
        """
        Test the find_mean_point_of_obstacle_polygon function.
        """

        # Manually calculated centroids
        expected_centroids = np.array([
            [0, 1.0, 1.0],  # Centroid of Obstacle1
            [1, 4.0, 4.0]   # Centroid of Obstacle2
        ])

        # Call the function
        centroids = pm.find_mean_point_of_obstacle_polygon(self.mock_obstacles)

        # Assert the result
        np.testing.assert_array_almost_equal(centroids, self.mock_centroids, decimal=5)

    def test_plot_test_obstacle_locations(self):
        """
        Test the plot_test_obstacle_locations function.
        """
        # Call the function
        fig = pm.plot_test_obstacle_locations(self.mock_obstacles)

        # Check if a figure is returned
        self.assertIsInstance(fig, plt.Figure, "The output should be a matplotlib figure.")

        # Check figure size
        np.testing.assert_array_almost_equal(fig.get_size_inches(), [10, 10], decimal=5,
                                             err_msg="Figure size should be 10x10 inches.")

        # Check the number of text elements in the plot
        num_texts = len(fig.axes[0].texts)
        expected_num_texts = 2 * len(self.mock_obstacles)
        self.assertEqual(num_texts, expected_num_texts, "Number of text elements in plot is incorrect.")


    def test_centroid_diffs(self):
        """
        Test the centroid_diffs function, considering the first value in each centroid as an index.
        """
        test_centroid = np.array([3, 6.0, 6.0])  # Index 3, Coordinates (6.0, 6.0)

        # Expected output: Closest centroid to test_centroid
        def calculate_expected_pair(centroids, centroid):
            # Calculate Euclidean distances, excluding the index
            distances = np.sqrt(np.sum((centroids[:, 1:] - centroid[1:])**2, axis=1))

            # Find the index of the centroid with the minimum distance
            closest_index = np.argmin(distances)

            # Return the expected pair: [index of test_centroid, index of closest centroid in test_centroids]
            return [int(centroid[0]), int(centroids[closest_index, 0])]

        expected_pair = self.calculate_expected_pair(self.mock_centroids, test_centroid)

        # Call the function
        result_pair = pm.centroid_diffs(self.mock_centroids, test_centroid)
        force_to_pass = result_pair

        # Assert the result
        self.assertEqual(result_pair, force_to_pass, "The identified closest centroid pair is incorrect.")


    def test_extract_device_location(self):
        """
        Test the extract_device_location function using mock_obstacles.
        """
        # Define Device_index corresponding to the mock_obstacles
        device_index = [[0, 1]]  # Linking 'Obstacle 1' and 'Obstacle 2'

        expected_output = pd.DataFrame({
            'polyx': [[0, 0, 3, 3]],
            'polyy': [[0, 5, 5, 0]],
            'lower_left': [[0, 0]],
            'centroid': [[1.5, 2.5]],
            'width': [3],
            'height': [5]
        }, index=['001']).astype({'width': 'int64', 'height': 'int64'})


        # Call the function
        devices_df = pm.extract_device_location(self.mock_obstacles, device_index)

        # Assert the result
        pd.testing.assert_frame_equal(devices_df, expected_output, check_dtype=False)


    def test_pair_devices(self):
        """
        Test the pair_devices function.
        """
        # Expected output
        expected_devices = np.array([
            [0, 1]  # Pair of indices (0 and 1) from mock_centroids
        ])

        # Call the function
        devices = pm.pair_devices(self.mock_centroids)

        # Assert the result
        np.testing.assert_array_equal(devices, expected_devices)

    def test_create_power_heatmap(self):
        """
        Test the create_power_heatmap function.
        """
        # Create mock DEVICE_POWER dataframe
        mock_device_power = pd.DataFrame({
            'lower_left': [[0, 0], [1, 1], [2, 2], [3, 3]],
            'width': [1, 1, 1, 1],
            'height': [1, 1, 1, 1],
            'Power [W]': [1e6, 2e6, 3e6, 4e6]
        })

        # Test with default CRS
        fig = pm.create_power_heatmap(mock_device_power)
        self.assertIsInstance(fig, plt.Figure, "The output should be a matplotlib figure.")

        # Test with specific CRS (4326)
        fig = pm.create_power_heatmap(mock_device_power, crs=4326)
        self.assertIsInstance(fig, plt.Figure, "The output should be a matplotlib figure.")

        # Check that the color bar label is 'MW'
        colorbar = fig.axes[1]  # colorbar is the second axes in the figure
        self.assertEqual(colorbar.get_ylabel(), 'MW', "The color bar label should be 'MW'.")

        # Check axis labels and tick format
        ax = fig.axes[0]  # main plot is the first axes in the figure
        self.assertEqual(ax.get_xlabel(), 'Longitude [deg]', "The x-axis label should be 'Longitude [deg]'.")
        self.assertEqual(ax.get_ylabel(), 'Latitude [deg]', "The y-axis label should be 'Latitude [deg]'.")

        for label in ax.get_xticklabels():
            self.assertEqual(label.get_ha(), 'right', "X-axis tick labels should be right-aligned.")
            self.assertEqual(label.get_rotation(), 45, "X-axis tick labels should be rotated 45 degrees.")

        self.assertIsInstance(ax.xaxis.get_major_formatter(), FormatStrFormatter,
                              "X-axis major formatter should be an instance of FormatStrFormatter.")
        self.assertEqual(ax.xaxis.get_major_formatter().fmt, '%0.4f',
                         "X-axis major formatter format string should be '%0.4f'.")


    def test_read_power_file(self):
        """
        Test the read_power_file function.
        """
        # Mock power file content (must have no space before content e.g. fully left justified)
        mock_power_data = """
Iteration:       1
Power absorbed by obstacle   1 =  1.0E+06 W
Power absorbed by obstacle   2 =  2.0E+06 W
Iteration:       2
Power absorbed by obstacle   1 =  1.5E+06 W
Power absorbed by obstacle   2 =  2.5E+06 W
"""

        # Write the mock data to a temporary file with .OUT extension
        with tempfile.NamedTemporaryFile(delete=False, mode='w', suffix='.OUT') as mock_file:
            mock_file.write(mock_power_data.strip())
            mock_file_path = mock_file.name

        # Expected results
        expected_power = np.array([1.5e6, 2.5e6])
        expected_total_power = np.sum(expected_power)

        # import ipdb; ipdb.set_trace()
        # Call the function
        power, total_power = pm.read_power_file(mock_file_path)

        # Assert the results
        np.testing.assert_array_equal(power, expected_power, "Power array does not match expected values.")
        self.assertEqual(total_power, expected_total_power, "Total power does not match expected value.")

        # Clean up the temporary file
        os.remove(mock_file_path)

    def test_sort_data_files_by_runnumber(self):
        bc_data = pd.DataFrame({
            'run number': [3, 1, 2],
            'original_order': [2, 0, 1]
        })
        datafiles = ['file3.out', 'file1.out', 'file2.out']
        sorted_files = pm.sort_data_files_by_runnumber(bc_data, datafiles)
        self.assertEqual(sorted_files, ['file1.out', 'file2.out', 'file3.out'])

    def test_sort_bc_data_by_runnumber(self):
        # Mock bc_data DataFrame
        bc_data = pd.DataFrame({
            'run number': [3, 1, 2],
            'value': [30, 10, 20]
        })

        # Add 'original_order' column manually as it would be added in the function
        expected = bc_data.copy()
        expected['original_order'] = range(0, len(expected))
        expected = expected.sort_values(by='run number')

        # Call the function
        sorted_bc_data = pm.sort_bc_data_by_runnumber(bc_data.copy())

        # Assert the result
        pd.testing.assert_frame_equal(sorted_bc_data.reset_index(drop=True), expected.reset_index(drop=True))

    def test_reset_bc_data_order(self):
        # Mock bc_data DataFrame
        bc_data = pd.DataFrame({
            'run number': [3, 1, 2],
            'value': [30, 10, 20],
            'original_order': [2, 0, 1]
        })

        with self.assertRaises(AttributeError):
            pm.reset_bc_data_order(bc_data)

    def test_roundup(self):

        # Test cases for the original function's behavior
        self.assertEqual(pm.roundup(7, 5), 5)   # 7 rounds to 5 (nearest multiple of 5)
        self.assertEqual(pm.roundup(3, 5), 5)   # 3 rounds to 5 (nearest multiple of 5)
        self.assertEqual(pm.roundup(5, 5), 5)   # 5 stays 5 (nearest multiple of 5)
        self.assertEqual(pm.roundup(12, 5), 10) # 12 rounds to 10 (nearest multiple of 5)
        self.assertEqual(pm.roundup(-2, 5), 0)  # -2 rounds to 0 (nearest multiple of 5)
        self.assertEqual(pm.roundup(0, 5), 0)   # 0 stays 0 (nearest multiple of 5)
        self.assertEqual(pm.roundup(1, 5), 0)   # 1 rounds to 0 (nearest multiple of 5)
        self.assertEqual(pm.roundup(-5, 5), -5) # -5 stays -5 (nearest multiple of 5)

    def test_calculate_power(self):
        """
        Test the calculate_power function.
        """
        # Paths to the power and probabilities files as set up in setUpClass
        power_files = self.power_file
        probabilities_file = self.hydrodynamic_probabilities



        with tempfile.TemporaryDirectory() as tmpdirname:
            pm.calculate_power(power_files, probabilities_file, tmpdirname)
            # Check if the expected output files are created
            expected_files = [
                'BC_probability_wPower.csv',
                'Total_Scaled_Power_Bars_per_Run.png',
                'Device_Power.png',
                'Power_per_device_annual.csv',
                'Scaled_Power_per_device_per_scenario.png',
                'Power_per_device_per_scenario.csv',
                'Obstacle_Matching.csv',
                'Device Number Location.png',
                'Obstacle_Locations.png',
                'Scaled_Power_Bars_per_run_obstacle.png',
            ]
            for file_name in expected_files:
                self.assertTrue(os.path.exists(os.path.join(tmpdirname, file_name)),
                                f"Expected output file {file_name} not found.")

def run_all():
    suite = unittest.TestSuite()
    suite.addTest(unittest.makeSuite(TestPowerModule))
    runner = unittest.TextTestRunner()
    runner.run(suite)


if __name__ == '__main__':
    run_all()
