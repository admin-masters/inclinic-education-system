<?php
// Enable error reporting
error_reporting(E_ALL);
ini_set('display_errors', 1);

include '../config/constants.php';

$servername = '13.234.88.80';
$username = 'test_doctor_u';
$password = 'V.D@-6*CwL0dmMP0';
$dbname = 'test_doctor';

// Create a connection to the database
$conn_other = new mysqli($servername, $username, $password, $dbname);
if ($conn_other->connect_error) {
    die('Connection failed: ' . $conn_other->connect_error);
}

// Get the brand_campaign_id from the request
$brand_campaign_id = isset($_GET['brand_campaign_id']) ? $_GET['brand_campaign_id'] : '';

// Fetch data for CSV

// Fetch unique field reps count
$queryFieldReps = "SELECT COUNT(DISTINCT field_id) AS unique_field_reps_count FROM field_reps WHERE brand_campaign_id = '$brand_campaign_id'";
$resultFieldReps = mysqli_query($conn, $queryFieldReps);
$uniqueFieldRepsCount = ($resultFieldReps && mysqli_num_rows($resultFieldReps) > 0) ? mysqli_fetch_assoc($resultFieldReps)['unique_field_reps_count'] : 0;

// Fetch unique doctors count
$queryDoctors = "SELECT COUNT(DISTINCT mobile_number) AS unique_doctors_count FROM doctors WHERE brand_campaign_id = '$brand_campaign_id'";
$resultDoctors = mysqli_query($conn, $queryDoctors);
$uniqueDoctorsCount = ($resultDoctors && mysqli_num_rows($resultDoctors) > 0) ? mysqli_fetch_assoc($resultDoctors)['unique_doctors_count'] : 0;

// Fetch unique field reps count for the last 7 days
$queryFieldRepsLast7Days = "SELECT COUNT(DISTINCT field_id) AS unique_field_reps_count_last_7_days FROM field_reps WHERE brand_campaign_id = '$brand_campaign_id' AND created_at >= DATE_SUB(CURDATE(), INTERVAL 7 DAY)";
$resultFieldRepsLast7Days = mysqli_query($conn, $queryFieldRepsLast7Days);
$uniqueFieldRepsCountLast7Days = ($resultFieldRepsLast7Days && mysqli_num_rows($resultFieldRepsLast7Days) > 0) ? mysqli_fetch_assoc($resultFieldRepsLast7Days)['unique_field_reps_count_last_7_days'] : 0;

// Fetch unique doctors count for the last 7 days
$queryDoctorsLast7Days = "SELECT COUNT(DISTINCT mobile_number) AS unique_doctors_count_last_7_days FROM doctors WHERE brand_campaign_id = '$brand_campaign_id' AND registration_date >= DATE_SUB(CURDATE(), INTERVAL 7 DAY)";
$resultDoctorsLast7Days = mysqli_query($conn, $queryDoctorsLast7Days);
$uniqueDoctorsCountLast7Days = ($resultDoctorsLast7Days && mysqli_num_rows($resultDoctorsLast7Days) > 0) ? mysqli_fetch_assoc($resultDoctorsLast7Days)['unique_doctors_count_last_7_days'] : 0;

// Fetch collateral distribution for all time
$queryCollateralDistribution = "
    SELECT 
        SUM(collateral_count = 1) AS one_collateral,
        SUM(collateral_count BETWEEN 2 AND 5) AS two_to_five_collaterals,
        SUM(collateral_count BETWEEN 6 AND 10) AS six_to_ten_collaterals,
        SUM(collateral_count > 10) AS more_than_ten_collaterals
    FROM (
        SELECT doctor_number, COUNT(DISTINCT collateral_id) AS collateral_count
        FROM collateral_transactions
        WHERE Brand_Campaign_ID = '$brand_campaign_id'
        GROUP BY doctor_number
    ) AS doctor_collateral_counts";
$resultCollateralDistribution = mysqli_query($conn, $queryCollateralDistribution);
if ($resultCollateralDistribution && mysqli_num_rows($resultCollateralDistribution) > 0) {
    $collateralCounts = mysqli_fetch_assoc($resultCollateralDistribution);
    $oneCollateralCount = $collateralCounts['one_collateral'];
    $twoToFiveCollateralsCount = $collateralCounts['two_to_five_collaterals'];
    $sixToTenCollateralsCount = $collateralCounts['six_to_ten_collaterals'];
    $moreThanTenCollateralsCount = $collateralCounts['more_than_ten_collaterals'];
} else {
    $oneCollateralCount = 0;
    $twoToFiveCollateralsCount = 0;
    $sixToTenCollateralsCount = 0;
    $moreThanTenCollateralsCount = 0;
}

// Fetch collateral distribution for the last 7 days
$queryCollateralDistributionLast7Days = "
    SELECT 
        SUM(collateral_count = 1) AS one_collateral,
        SUM(collateral_count BETWEEN 2 AND 5) AS two_to_five_collaterals,
        SUM(collateral_count BETWEEN 6 AND 10) AS six_to_ten_collaterals,
        SUM(collateral_count > 10) AS more_than_ten_collaterals
    FROM (
        SELECT doctor_number, COUNT(DISTINCT collateral_id) AS collateral_count
        FROM collateral_transactions
        WHERE Brand_Campaign_ID = '$brand_campaign_id' AND transaction_date >= DATE_SUB(NOW(), INTERVAL 7 DAY)
        GROUP BY doctor_number
    ) AS doctor_collateral_counts_last_7_days";
$resultCollateralDistributionLast7Days = mysqli_query($conn, $queryCollateralDistributionLast7Days);
if ($resultCollateralDistributionLast7Days && mysqli_num_rows($resultCollateralDistributionLast7Days) > 0) {
    $collateralCountsLast7Days = mysqli_fetch_assoc($resultCollateralDistributionLast7Days);
    $oneCollateralCountLast7Days = $collateralCountsLast7Days['one_collateral'];
    $twoToFiveCollateralsCountLast7Days = $collateralCountsLast7Days['two_to_five_collaterals'];
    $sixToTenCollateralsCountLast7Days = $collateralCountsLast7Days['six_to_ten_collaterals'];
    $moreThanTenCollateralsCountLast7Days = $collateralCountsLast7Days['more_than_ten_collaterals'];
} else {
    $oneCollateralCountLast7Days = 0;
    $twoToFiveCollateralsCountLast7Days = 0;
    $sixToTenCollateralsCountLast7Days = 0;
    $moreThanTenCollateralsCountLast7Days = 0;
}

// Fetch doctor engagement activity for all time
$queryDoctorEngagement = "
    SELECT 
        SUM(collateral_view_count = 1) AS one_collateral,
        SUM(collateral_view_count BETWEEN 2 AND 5) AS two_to_five_collaterals,
        SUM(collateral_view_count BETWEEN 6 AND 10) AS six_to_ten_collaterals,
        SUM(collateral_view_count > 10) AS more_than_ten_collaterals
    FROM (
        SELECT doctor_number, COUNT(DISTINCT collateral_id) AS collateral_view_count
        FROM collateral_transactions
        WHERE Brand_Campaign_ID = '$brand_campaign_id' AND viewed = 1
        GROUP BY doctor_number
    ) AS doctor_viewed_counts";
$resultDoctorEngagement = mysqli_query($conn, $queryDoctorEngagement);
if ($resultDoctorEngagement && mysqli_num_rows($resultDoctorEngagement) > 0) {
    $doctorEngagementCounts = mysqli_fetch_assoc($resultDoctorEngagement);
    $oneCollateralViewedCount = $doctorEngagementCounts['one_collateral'];
    $twoToFiveCollateralsViewedCount = $doctorEngagementCounts['two_to_five_collaterals'];
    $sixToTenCollateralsViewedCount = $doctorEngagementCounts['six_to_ten_collaterals'];
    $moreThanTenCollateralsViewedCount = $doctorEngagementCounts['more_than_ten_collaterals'];
} else {
    $oneCollateralViewedCount = 0;
    $twoToFiveCollateralsViewedCount = 0;
    $sixToTenCollateralsViewedCount = 0;
    $moreThanTenCollateralsViewedCount = 0;
}

// Fetch doctor engagement activity for the last 7 days
$queryDoctorEngagementLast7Days = "
    SELECT 
        SUM(collateral_view_count = 1) AS one_collateral,
        SUM(collateral_view_count BETWEEN 2 AND 5) AS two_to_five_collaterals,
        SUM(collateral_view_count BETWEEN 6 AND 10) AS six_to_ten_collaterals,
        SUM(collateral_view_count > 10) AS more_than_ten_collaterals
    FROM (
        SELECT doctor_number, COUNT(DISTINCT collateral_id) AS collateral_view_count
        FROM collateral_transactions
        WHERE Brand_Campaign_ID = '$brand_campaign_id' AND viewed = 1 AND transaction_date >= DATE_SUB(NOW(), INTERVAL 7 DAY)
        GROUP BY doctor_number
    ) AS doctor_viewed_counts_last_7_days";
$resultDoctorEngagementLast7Days = mysqli_query($conn, $queryDoctorEngagementLast7Days);
if ($resultDoctorEngagementLast7Days && mysqli_num_rows($resultDoctorEngagementLast7Days) > 0) {
    $doctorEngagementCountsLast7Days = mysqli_fetch_assoc($resultDoctorEngagementLast7Days);
    $oneCollateralViewedCountLast7Days = $doctorEngagementCountsLast7Days['one_collateral'];
    $twoToFiveCollateralsViewedCountLast7Days = $doctorEngagementCountsLast7Days['two_to_five_collaterals'];
    $sixToTenCollateralsViewedCountLast7Days = $doctorEngagementCountsLast7Days['six_to_ten_collaterals'];
    $moreThanTenCollateralsViewedCountLast7Days = $doctorEngagementCountsLast7Days['more_than_ten_collaterals'];
} else {
    $oneCollateralViewedCountLast7Days = 0;
    $twoToFiveCollateralsViewedCountLast7Days = 0;
    $sixToTenCollateralsViewedCountLast7Days = 0;
    $moreThanTenCollateralsViewedCountLast7Days = 0;
}

// CSV headers
header('Content-Type: text/csv; charset=utf-8');
header('Content-Disposition: attachment; filename=report.csv');

// Open output stream
$output = fopen('php://output', 'w');

// Write column headers and data to CSV
fputcsv($output, ['Field Rep Activity', 'Last 7 Days', 'All Time']);
fputcsv($output, ['Total Number of Unique Field Reps Registered', $uniqueFieldRepsCountLast7Days, $uniqueFieldRepsCount]);
fputcsv($output, ['Total Number of Unique Doctors Registered', $uniqueDoctorsCountLast7Days, $uniqueDoctorsCount]);

fputcsv($output, []); // Blank line for separation

fputcsv($output, ['Collateral Distribution', 'Last 7 Days', 'All Time']);
fputcsv($output, ['1 collateral', $oneCollateralCountLast7Days, $oneCollateralCount]);
fputcsv($output, ['2-5 collaterals', $twoToFiveCollateralsCountLast7Days, $twoToFiveCollateralsCount]);
fputcsv($output, ['6-10 collaterals', $sixToTenCollateralsCountLast7Days, $sixToTenCollateralsCount]);
fputcsv($output, ['More than 10 collaterals', $moreThanTenCollateralsCountLast7Days, $moreThanTenCollateralsCount]);

fputcsv($output, []); // Blank line for separation

fputcsv($output, ['Doctor Engagement Activity', 'Last 7 Days', 'All Time']);
fputcsv($output, ['1 collateral viewed', $oneCollateralViewedCountLast7Days, $oneCollateralViewedCount]);
fputcsv($output, ['2-5 collaterals viewed', $twoToFiveCollateralsViewedCountLast7Days, $twoToFiveCollateralsViewedCount]);
fputcsv($output, ['6-10 collaterals viewed', $sixToTenCollateralsViewedCountLast7Days, $sixToTenCollateralsViewedCount]);
fputcsv($output, ['More than 10 collaterals viewed', $moreThanTenCollateralsViewedCountLast7Days, $moreThanTenCollateralsViewedCount]);

// Close the output stream
fclose($output);

// Close the database connection
mysqli_close($conn);
?>
