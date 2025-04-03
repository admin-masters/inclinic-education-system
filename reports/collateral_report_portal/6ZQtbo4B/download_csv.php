<?php
ini_set('display_errors', 1);
ini_set('display_startup_errors', 1);
error_reporting(E_ALL);

include '../../config/constants.php';   // Ensure this file establishes the database connection correctly

// Assuming $brand_campaign_id holds the specific brand_campaign_id you want to fetch
$brand_campaign_id = isset($_GET['brand_campaign_id']) ? $_GET['brand_campaign_id'] : ''; 

// CSV filename
$filename = 'report_data_' . $brand_campaign_id . '.csv';

// Set headers to download the file rather than display
header('Content-Type: text/csv; charset=utf-8');
header('Content-Disposition: attachment; filename=' . $filename);

// Create a file pointer connected to the output stream
$output = fopen('php://output', 'w');

// Output column headings (added 354)
fputcsv($output, ['Field ID', 'Field Rep Gmail ID', 'Manager', 'State', 'Number of Doctors Registered', 'Doctor Name', 'Doctor Number', '216', '249', '217', '321', '231', '302', '317', '331', '354', '300', '343', '347', '355', '357', '448', '394']);


// Fetch records from the collateral_transactions table for the given brand_campaign_id
$query = "SELECT * FROM collateral_transactions WHERE Brand_Campaign_ID = '$brand_campaign_id' ORDER BY field_id ASC";
$result = mysqli_query($conn, $query);

if ($result) {
    // Added 354 to collateral_ids
    $collateral_ids = [216, 249, 217, 321, 231, 302, 317, 331, 354, 300, 343, 347, 355, 357, 448, 394];

    $csv_file_path = 'csvfile.csv'; // Replace with the actual path to your CSV file
    $csv_data = array_map('str_getcsv', file($csv_file_path));
    $csv_headers = array_shift($csv_data); // Get headers

    $csv_map = [];
    foreach ($csv_data as $row) {
        $row_assoc = array_combine($csv_headers, $row);
        $field_id = $row_assoc['Field_id']; // Correct field ID header based on CSV
        $csv_map[$field_id] = $row_assoc; // Map field_id to manager and state
    }

    $doctor_count = []; // To store the count of distinct doctors for each field_id
    $data = []; // To store aggregated data

    while ($row = mysqli_fetch_assoc($result)) {
        $field_id = $row['field_id'];
        $doctor_number = $row['doctor_number'];
        $collateral_id = $row['collateral_id'];

        // Fetch the doctor name from the doctors table using doctor_number
        $doctor_name = '';
        if (!empty($doctor_number)) {
            $doctor_query = "SELECT name AS doctor_name FROM doctors WHERE mobile_number = '$doctor_number'";
            $doctor_result = mysqli_query($conn, $doctor_query);
            if ($doctor_result && mysqli_num_rows($doctor_result) > 0) {
                $doctor_name = mysqli_fetch_assoc($doctor_result)['doctor_name'] ?? '';
            }
            mysqli_free_result($doctor_result);
        }

        // Fetch the field rep gmail from the field_reps table using field_id
        $field_rep_gmail = '';
        if (!empty($field_id)) {
            $rep_query = "SELECT gmail_id FROM field_reps WHERE field_id = '$field_id'";
            $rep_result = mysqli_query($conn, $rep_query);
            if ($rep_result && mysqli_num_rows($rep_result) > 0) {
                $field_rep_gmail = mysqli_fetch_assoc($rep_result)['gmail_id'] ?? '';
            }
            mysqli_free_result($rep_result);
        }

        // Fetch the manager and state from the CSV data
        $manager = isset($csv_map[$field_id]['Manager Name']) ? $csv_map[$field_id]['Manager Name'] : '';
        $state = isset($csv_map[$field_id]['State']) ? $csv_map[$field_id]['State'] : '';

        // Count the number of distinct doctors registered by each field_id
        if (!isset($doctor_count[$field_id])) {
            // Fetch distinct doctor numbers for the current field_id
            $distinct_doctor_query = "SELECT COUNT(DISTINCT mobile_number) AS doctor_count FROM doctors WHERE field_id = '$field_id'";
            $distinct_doctor_result = mysqli_query($conn, $distinct_doctor_query);
            $doctor_count[$field_id] = mysqli_fetch_assoc($distinct_doctor_result)['doctor_count'] ?? 0;
            mysqli_free_result($distinct_doctor_result);
        }

        $key = $field_id . '-' . $doctor_number; // Create a unique key for each field ID and doctor combination

        // Check if the entry for this field_id and doctor already exists
        if (!isset($data[$key])) {
            $collateral_dates = array_fill_keys($collateral_ids, '');
            $data[$key] = [
                'field_id' => $field_id,
                'field_rep_gmail' => $field_rep_gmail,
                'manager' => $manager,
                'state' => $state,
                'number_of_doctors_registered' => $doctor_count[$field_id],
                'doctor_name' => $doctor_name,
                'doctor_number' => $doctor_number,
                'collateral_dates' => $collateral_dates
            ];
        }

        // Append the date to the appropriate collateral ID column
        $transaction_date = date('Y-m-d', strtotime($row['transaction_date']));
        if (in_array($collateral_id, $collateral_ids)) {
            if (strpos($data[$key]['collateral_dates'][$collateral_id], $transaction_date) === false) {
                if (!empty($data[$key]['collateral_dates'][$collateral_id])) {
                    $data[$key]['collateral_dates'][$collateral_id] .= ', ' . $transaction_date;
                } else {
                    $data[$key]['collateral_dates'][$collateral_id] = $transaction_date;
                }
            }
        }
    }

    // Write the aggregated data to the CSV file (added 354)
    foreach ($data as $row) {
        fputcsv($output, [
            $row['field_id'],
            $row['field_rep_gmail'],
            $row['manager'],
            $row['state'],
            $row['number_of_doctors_registered'],
            $row['doctor_name'],
            $row['doctor_number'],
            $row['collateral_dates'][216],
            $row['collateral_dates'][249],
            $row['collateral_dates'][217],
            $row['collateral_dates'][321],
            $row['collateral_dates'][231],
            $row['collateral_dates'][302],
            $row['collateral_dates'][317],
            $row['collateral_dates'][331],
            $row['collateral_dates'][354],  
            $row['collateral_dates'][300], 
            $row['collateral_dates'][343],
            $row['collateral_dates'][347],
            $row['collateral_dates'][355],
            $row['collateral_dates'][357],
            $row['collateral_dates'][448],
            $row['collateral_dates'][394],

        ]);
    }

    mysqli_free_result($result);
} else {
    echo "Error executing query: " . mysqli_error($conn);
}

mysqli_close($conn);
?>