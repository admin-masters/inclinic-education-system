<?php
// Display errors for debugging
ini_set('display_errors', 1);
ini_set('display_startup_errors', 1);
error_reporting(E_ALL);

include '../../config/constants.php'; // Include your DB config

// Set the header to force download of the CSV file
header('Content-Type: text/csv');
header('Content-Disposition: attachment;filename=report.csv');

// File path to the original CSV file
$csvFilePath = 'Report.csv';

// Open the output stream for writing the CSV content
$output = fopen('php://output', 'w');

// Add the headers for the CSV file
$headers = [
    'State', 'Empcode', 'Position Code', 'Empname', 'HQ', 'Emp Mob No.', 'MCL No',
    'Doctors Name', 'Qualification', 'Mobile', 'Collateral Shared with Dr.',
    'Collateral Viewed by Dr.', 'Collateral Viewed by Dr. Duration of Time', 'Date when Viewed'
];
fputcsv($output, $headers);

// Function to fetch collateral transaction dates (same as in your main file)
function fetchCollateralSharedDates($field_id, $doctor_number, $conn) {
    $dates = 'N/A';
    $query = "SELECT GROUP_CONCAT(transaction_date SEPARATOR ', ') AS dates 
              FROM collateral_transactions 
              WHERE field_id = ? 
              AND doctor_number = ? 
              AND comment = 'Collateral Shared'";
    $stmt = $conn->prepare($query);
    $stmt->bind_param('ss', $field_id, $doctor_number);
    $stmt->execute();
    $stmt->bind_result($dateList);
    if ($stmt->fetch()) {
        $dates = $dateList ? $dateList : 'N/A';
    }
    $stmt->close();
    return $dates;
}

function fetchCollateralViewedDates($field_id, $doctor_number, $conn) {
    $dates = 'N/A';
    $query = "SELECT GROUP_CONCAT(transaction_date SEPARATOR ', ') AS dates 
              FROM collateral_transactions 
              WHERE field_id = ? 
              AND doctor_number = ? 
              AND comment = 'collateral viewed'";
    $stmt = $conn->prepare($query);
    $stmt->bind_param('ss', $field_id, $doctor_number);
    $stmt->execute();
    $stmt->bind_result($dateList);
    if ($stmt->fetch()) {
        $dates = $dateList ? $dateList : 'N/A';
    }
    $stmt->close();
    return $dates;
}

function fetchVideoViewedDates($field_id, $doctor_number, $conn) {
    $dates = 'N/A';
    $query = "SELECT GROUP_CONCAT(transaction_date SEPARATOR ', ') AS dates 
              FROM collateral_transactions 
              WHERE field_id = ? 
              AND doctor_number = ? 
              AND comment = 'Video Viewed'";
    $stmt = $conn->prepare($query);
    $stmt->bind_param('ss', $field_id, $doctor_number);
    $stmt->execute();
    $stmt->bind_result($dateList);
    if ($stmt->fetch()) {
        $dates = $dateList ? $dateList : 'N/A';
    }
    $stmt->close();
    return $dates;
}

function fetchCollateralViewedDuration($field_id, $doctor_number, $conn) {
    $viewed_duration = 'N/A';
    $viewedValue = null;
    $query = "SELECT MAX(video_pec) AS viewed_duration 
              FROM collateral_transactions 
              WHERE field_id = ? 
              AND doctor_number = ? 
              AND comment = 'Video Viewed'";
    $stmt = $conn->prepare($query);
    $stmt->bind_param('ss', $field_id, $doctor_number);
    $stmt->execute();
    $stmt->bind_result($viewedValue);
    if ($stmt->fetch()) {
        if ($viewedValue == 1) {
            $viewed_duration = ">50%";
        } elseif ($viewedValue == 2) {
            $viewed_duration = "<50%";
        } elseif ($viewedValue == 3) {
            $viewed_duration = "100%";
        } else {
            $viewed_duration = 'N/A';
        }
    }
    $stmt->close();
    return $viewed_duration;
}

// Load CSV data and output to new CSV
if (($handle = fopen($csvFilePath, "r")) !== FALSE) {
    $header = fgetcsv($handle); // Skip header

    // Process each row in the original CSV
    while (($row = fgetcsv($handle)) !== FALSE) {
        $field_id = $row[1]; // Assuming Empcode is the second column
        $doctor_number = $row[9]; // Assuming Mobile is the 10th column

        // Fetch collateral shared, viewed dates, and viewed duration from the database
        $collateral_shared_dates = fetchCollateralSharedDates($field_id, $doctor_number, $conn);
        $collateral_viewed_dates = fetchCollateralViewedDates($field_id, $doctor_number, $conn);
        $collateral_viewed_duration = fetchCollateralViewedDuration($field_id, $doctor_number, $conn);
        $video_viewed_dates = fetchVideoViewedDates($field_id, $doctor_number, $conn);

        // Append the additional details to the row
        $row[] = $collateral_shared_dates;
        $row[] = $collateral_viewed_dates;
        $row[] = $collateral_viewed_duration;
        $row[] = $video_viewed_dates;

        // Output the row to the CSV
        fputcsv($output, $row);
    }

    fclose($handle);
}

// Close output stream
fclose($output);
exit;
?>
