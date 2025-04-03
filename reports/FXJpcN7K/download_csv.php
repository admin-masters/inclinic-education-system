<?php
error_reporting(E_ALL); // Report all types of errors
ini_set('display_errors', 1); // Display errors on the webpage

include '../config/constants.php';

// Database connection
$servername = '13.234.88.80';
$username = 'test_doctor_u';
$password = 'V.D@-6*CwL0dmMP0';
$dbname = 'test_doctor';

$conn_other = new mysqli($servername, $username, $password, $dbname);

if ($conn_other->connect_error) {
    die('Connection failed: ' . $conn_other->connect_error);
}

$brand_campaign_id = isset($_GET['brand_campaign_id']) ? $_GET['brand_campaign_id'] : 'FXJpcN7K';

// Fetch start date from brand_campaigns table
$query = "SELECT start_date FROM brand_campaigns WHERE brand_campaign_id = '$brand_campaign_id'";
$result = mysqli_query($conn_other, $query);
if ($result && mysqli_num_rows($result) > 0) {
    $row = mysqli_fetch_assoc($result);
    $startDate = $row['start_date'];
    $endDate = date('Y-m-d');
} else {
    $startDate = "N/A";
    $endDate = "N/A";
}

// Fetch the count of unique field_ids from the field_reps table
$queryFieldReps = "SELECT COUNT(DISTINCT field_id) AS unique_field_reps_count FROM field_reps WHERE brand_campaign_id = '$brand_campaign_id'";
$resultFieldReps = mysqli_query($conn, $queryFieldReps);
$uniqueFieldRepsCount = ($resultFieldReps && mysqli_num_rows($resultFieldReps) > 0) ? mysqli_fetch_assoc($resultFieldReps)['unique_field_reps_count'] : 0;

// Fetch the count of unique mobile_numbers from the doctors table
$queryDoctors = "SELECT COUNT(DISTINCT mobile_number) AS unique_doctors_count FROM doctors WHERE brand_campaign_id = '$brand_campaign_id'";
$resultDoctors = mysqli_query($conn, $queryDoctors);
$uniqueDoctorsCount = ($resultDoctors && mysqli_num_rows($resultDoctors) > 0) ? mysqli_fetch_assoc($resultDoctors)['unique_doctors_count'] : 0;

// Fetch doctor_number count for each collateral
$queryCollateral272 = "SELECT COUNT(DISTINCT doctor_number) AS collateral_272_count FROM collateral_transactions WHERE collateral_id = 272 AND Brand_Campaign_ID = '$brand_campaign_id'";
$resultCollateral272 = mysqli_query($conn, $queryCollateral272);
$collateral272Count = ($resultCollateral272 && mysqli_num_rows($resultCollateral272) > 0) ? mysqli_fetch_assoc($resultCollateral272)['collateral_272_count'] : 0;

$queryCollateral276 = "SELECT COUNT(DISTINCT doctor_number) AS collateral_276_count FROM collateral_transactions WHERE collateral_id = 276 AND Brand_Campaign_ID = '$brand_campaign_id'";
$resultCollateral276 = mysqli_query($conn, $queryCollateral276);
$collateral276Count = ($resultCollateral276 && mysqli_num_rows($resultCollateral276) > 0) ? mysqli_fetch_assoc($resultCollateral276)['collateral_276_count'] : 0;

$queryCollateral273 = "SELECT COUNT(DISTINCT doctor_number) AS collateral_273_count FROM collateral_transactions WHERE collateral_id = 273 AND Brand_Campaign_ID = '$brand_campaign_id'";
$resultCollateral273 = mysqli_query($conn, $queryCollateral273);
$collateral273Count = ($resultCollateral273 && mysqli_num_rows($resultCollateral273) > 0) ? mysqli_fetch_assoc($resultCollateral273)['collateral_273_count'] : 0;

// Fetch the sum of 'viewed' for each collateral
$queryViewed272 = "SELECT SUM(viewed) AS collateral_272_viewed FROM collateral_transactions WHERE collateral_id = 272 AND Brand_Campaign_ID = '$brand_campaign_id'";
$resultViewed272 = mysqli_query($conn, $queryViewed272);
$collateral272Viewed = ($resultViewed272 && mysqli_num_rows($resultViewed272) > 0) ? mysqli_fetch_assoc($resultViewed272)['collateral_272_viewed'] : 0;

$queryViewed276 = "SELECT SUM(viewed) AS collateral_276_viewed FROM collateral_transactions WHERE collateral_id = 276 AND Brand_Campaign_ID = '$brand_campaign_id'";
$resultViewed276 = mysqli_query($conn, $queryViewed276);
$collateral276Viewed = ($resultViewed276 && mysqli_num_rows($resultViewed276) > 0) ? mysqli_fetch_assoc($resultViewed276)['collateral_276_viewed'] : 0;

$queryViewed273 = "SELECT SUM(viewed) AS collateral_273_viewed FROM collateral_transactions WHERE collateral_id = 273 AND Brand_Campaign_ID = '$brand_campaign_id'";
$resultViewed273 = mysqli_query($conn, $queryViewed273);
$collateral273Viewed = ($resultViewed273 && mysqli_num_rows($resultViewed273) > 0) ? mysqli_fetch_assoc($resultViewed273)['collateral_273_viewed'] : 0;

// Close the connection
mysqli_close($conn);

// Prepare CSV content
header('Content-Type: text/csv; charset=utf-8');
header('Content-Disposition: attachment; filename=report_' . $brand_campaign_id . '.csv');

$output = fopen('php://output', 'w');

// Add the headers
fputcsv($output, ['Field Rep Activity']);
fputcsv($output, ['Period', "$startDate - $endDate"]);
fputcsv($output, ['Total Number of Unique Field Reps Registered', $uniqueFieldRepsCount]);
fputcsv($output, ['Total Number of Unique Doctors Registered', $uniqueDoctorsCount]);

// Add a blank line for separation
fputcsv($output, []);

// Add the headers for collateral activity
fputcsv($output, ['Collateral Activity']);
fputcsv($output, ['Collateral Name', "Number of doctors who have received the collateral ($startDate - $endDate)", "Number of doctors who have viewed collateral ($startDate - $endDate)"]);

// Add the data for collateral 272
fputcsv($output, ['Mini CME 1 Managing High-Volume Pediatric Diarrhoea', $collateral272Count, $collateral272Viewed]);

// Add the data for collateral 276
fputcsv($output, ['Case Study on conditions linked to diarrhea and nutrition - Issue 1', $collateral276Count, $collateral276Viewed]);

// Add the data for collateral 273
fputcsv($output, ['Mini CME Issue 2 on Understanding Diarrhoea and the Role of Antibiotics in Children', $collateral273Count, $collateral273Viewed]);

// Close the output stream
fclose($output);
exit();
?>
