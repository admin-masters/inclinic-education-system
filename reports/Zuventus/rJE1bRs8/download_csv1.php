<?php
ini_set('display_errors', 1);
ini_set('display_startup_errors', 1);
error_reporting(E_ALL);

// Include your constants or database connection if necessary
include '../../config/constants.php'; 

// Get parameters from the request
$brand_campaign_id = isset($_GET['brand_campaign_id']) ? $_GET['brand_campaign_id'] : '';
$start_date = isset($_GET['start_date']) ? $_GET['start_date'] : '';
$end_date = isset($_GET['end_date']) ? $_GET['end_date'] : '';

// File name for the output
$filename = "Filtered_Report_" . date('Y-m-d') . ".csv";

// Set headers for file download
header('Content-Type: text/csv');
header('Content-Disposition: attachment; filename="' . $filename . '"');

// Output the CSV header
$output = fopen('php://output', 'w');
fputcsv($output, ['State', 'Empcode', 'Position Code', 'Empname', 'HQ', 'Emp Mob No.', 'MCL No', 'Number of Drs', 'Collateral Shared with Dr.', 'Collateral Viewed by Drs.']);

// Load the CSV data
$csvFilePath = 'Report.csv'; // Ensure this is the correct path to your CSV file

if (($handle = fopen($csvFilePath, "r")) !== FALSE) {
    $header = fgetcsv($handle); // Skip the header row
    $empcodeCounts = []; // Array to hold counts by Empcode
    $doctorCounts = [];
    $collateralCounts = [];
    $collateralViewedCounts = [];

    // Fetch doctor counts from the database based on the brand_campaign_id
    $doctorQuery = "
        SELECT field_id, COUNT(DISTINCT mobile_number) AS doctor_count
    FROM doctors
    WHERE Brand_Campaign_ID = ?
    AND registration_date >= '2025-03-01'
    AND registration_date <= CURDATE()
    GROUP BY field_id
    ";
    $stmt = $conn->prepare($doctorQuery);
    $stmt->bind_param("s", $brand_campaign_id);
    $stmt->execute();
    $result = $stmt->get_result();
    while ($row = $result->fetch_assoc()) {
        $doctorCounts[$row['field_id']] = $row['doctor_count'];
    }

    // Fetch collateral counts from the database
    $collateralQuery = "
        SELECT field_id, COUNT(DISTINCT doctor_number, collateral_id) AS unique_doctor_count
    FROM collateral_transactions
    WHERE Brand_Campaign_ID = ?
    AND transaction_date >= '2025-03-01'
    AND transaction_date <= CURDATE()
    GROUP BY field_id
    ";
    $stmt = $conn->prepare($collateralQuery);
    $stmt->bind_param("s", $brand_campaign_id);
    $stmt->execute();
    $result = $stmt->get_result();
    while ($row = $result->fetch_assoc()) {
        $collateralCounts[$row['field_id']] = $row['unique_doctor_count'];
    }

    // Fetch collateral viewed counts from the database
    $collateralViewedQuery = "
         SELECT field_id, COUNT(DISTINCT doctor_number, collateral_id) AS unique_viewed_doctor_count
    FROM collateral_transactions
    WHERE Brand_Campaign_ID = ?
    AND comment = 'collateral viewed'
    AND transaction_date >= '2025-03-01'
    AND transaction_date <= CURDATE()
    GROUP BY field_id
    ";
    $stmt = $conn->prepare($collateralViewedQuery);
    $stmt->bind_param("s", $brand_campaign_id);
    $stmt->execute();
    $result = $stmt->get_result();
    while ($row = $result->fetch_assoc()) {
        $collateralViewedCounts[$row['field_id']] = $row['unique_viewed_doctor_count'];
    }

    // Initialize variables for state totals
    $lastState = null;
    $stateTotals = [
        'doctor_count' => 0,
        'collateral_count' => 0,
        'collateral_viewed_count' => 0,
    ];

    // Iterate over the CSV data to fill in the rows without pagination
    while (($row = fgetcsv($handle)) !== FALSE) {
        $empcode = $row[1];
        $state = $row[0]; // Assuming the State is in the first column

        // Initialize counts for the current Empcode if not already set
        if (!isset($empcodeCounts[$empcode])) {
            $empcodeCounts[$empcode] = [
                'doctor_count' => isset($doctorCounts[$empcode]) ? $doctorCounts[$empcode] : 0,
                'collateral_count' => isset($collateralCounts[$empcode]) ? $collateralCounts[$empcode] : 0,
                'collateral_viewed_count' => isset($collateralViewedCounts[$empcode]) ? $collateralViewedCounts[$empcode] : 0,
            ];
        }

        // If the state changes, print the totals for the last state
        if ($lastState !== null && $lastState !== $state) {
            fputcsv($output, [
                'State Total for ' . $lastState, '', '', '', '', '', '', 
                $stateTotals['doctor_count'], 
                $stateTotals['collateral_count'], 
                $stateTotals['collateral_viewed_count']
            ]);

            // Reset state totals for the new state
            $stateTotals = [
                'doctor_count' => 0,
                'collateral_count' => 0,
                'collateral_viewed_count' => 0,
            ];
        }

        // Update the state totals
        $stateTotals['doctor_count'] += $empcodeCounts[$empcode]['doctor_count'];
        $stateTotals['collateral_count'] += $empcodeCounts[$empcode]['collateral_count'];
        $stateTotals['collateral_viewed_count'] += $empcodeCounts[$empcode]['collateral_viewed_count'];

        // Output the current row to the CSV file
        fputcsv($output, [
            $row[0], // State
            $row[1], // Empcode
            $row[2], // Position Code
            $row[3], // Empname
            $row[4], // HQ
            $row[5], // Emp Mob No.
            $row[6], // MCL No
            $empcodeCounts[$empcode]['doctor_count'], // Number of Drs
            $empcodeCounts[$empcode]['collateral_count'], // Collateral Shared with Dr.
            $empcodeCounts[$empcode]['collateral_viewed_count'], // Collateral Viewed by Drs.
        ]);

        $lastState = $state; // Update the last state
    }

    // After finishing reading the file, output totals for the last state if applicable
    if ($lastState !== null) {
        fputcsv($output, [
            'State Total for ' . $lastState, '', '', '', '', '', '', 
            $stateTotals['doctor_count'], 
            $stateTotals['collateral_count'], 
            $stateTotals['collateral_viewed_count']
        ]);
    }

    fclose($handle);
}

// Close database connection
$stmt->close();
$conn->close();
fclose($output);
?>
