<?php
ini_set('display_errors', 1);
ini_set('display_startup_errors', 1);
error_reporting(E_ALL);
include '../../config/constants.php';

$brand_campaign_id = isset($_GET['brand_campaign_id']) ? $_GET['brand_campaign_id'] : '';
$start_date = isset($_GET['start_date']) ? $_GET['start_date'] : '';
$end_date = isset($_GET['end_date']) ? $_GET['end_date'] : '';

if ($brand_campaign_id === '') {
    die("Brand Campaign ID is required.");
}

header('Content-Type: text/csv');
header('Content-Disposition: attachment;filename="field_reps_data.csv"');

// Create a file pointer connected to the output stream
$output = fopen('php://output', 'w');

// Output column headings
fputcsv($output, ['Field ID', 'Last 7 Days Count', 'Cumulative Count', 'Region']);

$region_map = [];
if (($handle = fopen("Region.csv", "r")) !== false) {
    // Skip the header
    fgetcsv($handle);
    while (($data = fgetcsv($handle)) !== false) {
        $region_map[$data[1]] = $data[0]; // Field ID as key and Region as value
    }
    fclose($handle);
}


// Prepare the SQL query to fetch field_ids with date filtering on created_at
$query = "SELECT DISTINCT field_id FROM field_reps WHERE brand_campaign_id = ?";
if ($start_date && $end_date) {
    // Use DATE(created_at) to filter by date only (ignoring time part)
    $query .= " AND DATE(created_at) BETWEEN ? AND ?";
}

// Use prepared statements to prevent SQL injection
$stmt = $conn->prepare($query);

if ($start_date && $end_date) {
    $stmt->bind_param("sss", $brand_campaign_id, $start_date, $end_date);
} else {
    $stmt->bind_param("s", $brand_campaign_id);
}

$stmt->execute();
$result = $stmt->get_result();

// Fetch the field_ids
while ($row = $result->fetch_assoc()) {
    $field_id = $row['field_id'];

    // Prepare the SQL queries to fetch counts from the doctors table with date filtering
    $last_7_days_count_query = "SELECT COUNT(mobile_number) AS last_7_days_count 
                                FROM doctors 
                                WHERE field_id = ? 
                                AND Brand_Campaign_ID = ? 
                                AND registration_date >= DATE_SUB(CURDATE(), INTERVAL 7 DAY)";

    $cumulative_count_query = "SELECT COUNT(mobile_number) AS cumulative_count 
                               FROM doctors 
                               WHERE field_id = ? 
                               AND Brand_Campaign_ID = ?";
    if ($start_date && $end_date) {
        $cumulative_count_query .= " AND registration_date BETWEEN ? AND ?";
    }

    // Get the last 7 days count
    $stmt_last_7_days = $conn->prepare($last_7_days_count_query);
    $stmt_last_7_days->bind_param("ss", $field_id, $brand_campaign_id);
    $stmt_last_7_days->execute();
    $result_last_7_days = $stmt_last_7_days->get_result();
    $last_7_days_count = $result_last_7_days->fetch_assoc()['last_7_days_count'];

    // Get the cumulative count
    if ($start_date && $end_date) {
        $stmt_cumulative = $conn->prepare($cumulative_count_query);
        $stmt_cumulative->bind_param("ssss", $field_id, $brand_campaign_id, $start_date, $end_date);
    } else {
        $stmt_cumulative = $conn->prepare($cumulative_count_query);
        $stmt_cumulative->bind_param("ss", $field_id, $brand_campaign_id);
    }

    $stmt_cumulative->execute();
    $result_cumulative = $stmt_cumulative->get_result();
    $cumulative_count = $result_cumulative->fetch_assoc()['cumulative_count'];

    // Determine the region using the CSV mapping
    $region = isset($region_map[$field_id]) ? $region_map[$field_id] : '-';

    // Write row to CSV
    fputcsv($output, [$field_id, $last_7_days_count, $cumulative_count, $region]);

    // Free results and close statements
    $stmt_last_7_days->close();
    $stmt_cumulative->close();
}

// Free result and close statement
$stmt->close();

// Close the output stream
fclose($output);
exit();
