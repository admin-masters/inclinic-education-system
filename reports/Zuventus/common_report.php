<?php
error_reporting(E_ALL); // Report all types of errors
ini_set('display_errors', 1); // Display errors on the webpage

include '../config/constants.php';

$servername = '13.234.88.80';
$username = 'test_doctor_u';
$password = 'V.D@-6*CwL0dmMP0';
$dbname = 'test_doctor';

$conn_other = new mysqli($servername, $username, $password, $dbname);

if ($conn_other->connect_error) {

    die('Connection failed: ' . $conn_other->connect_error);
}
$brand_campaign_id = isset($_GET['brand_campaign_id']) ? $_GET['brand_campaign_id'] : ''; // Replace with your desired brand_campaign_id

// Fetch start date from the brand_campaigns table
$query = "SELECT start_date FROM brand_campaigns WHERE brand_campaign_id = '$brand_campaign_id'";
$result = mysqli_query($conn_other, $query);

if ($result && mysqli_num_rows($result) > 0) { // Check if query executed and returned results
    $row = mysqli_fetch_assoc($result);
    $startDate = $row['start_date'];
    $endDate = date('Y-m-d');
} else {
    // Handle query error or no results
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

// Fetch the count of unique field_ids from the field_reps table for the last 7 days
$queryFieldRepsLast7Days = "SELECT COUNT(DISTINCT field_id) AS unique_field_reps_count_last_7_days FROM field_reps WHERE brand_campaign_id = '$brand_campaign_id' AND created_at >= DATE_SUB(CURDATE(), INTERVAL 7 DAY)";
$resultFieldRepsLast7Days = mysqli_query($conn, $queryFieldRepsLast7Days);
$uniqueFieldRepsCountLast7Days = ($resultFieldRepsLast7Days && mysqli_num_rows($resultFieldRepsLast7Days) > 0) ? mysqli_fetch_assoc($resultFieldRepsLast7Days)['unique_field_reps_count_last_7_days'] : 0;

// Fetch the count of unique mobile_numbers from the doctors table for the last 7 days
$queryDoctorsLast7Days = "SELECT COUNT(DISTINCT mobile_number) AS unique_doctors_count_last_7_days FROM doctors WHERE brand_campaign_id = '$brand_campaign_id' AND registration_date >= DATE_SUB(CURDATE(), INTERVAL 7 DAY)";
$resultDoctorsLast7Days = mysqli_query($conn, $queryDoctorsLast7Days);
$uniqueDoctorsCountLast7Days = ($resultDoctorsLast7Days && mysqli_num_rows($resultDoctorsLast7Days) > 0) ? mysqli_fetch_assoc($resultDoctorsLast7Days)['unique_doctors_count_last_7_days'] : 0;

// Fetch unique (doctor_number, collateral_id) for that Brand_Campaign_ID and categorize them for all time
$queryCollateralDistribution = "
    SELECT 
        SUM(collateral_count = 1) AS one_collateral,
        SUM(collateral_count BETWEEN 2 AND 5) AS two_to_five_collaterals,
        SUM(collateral_count BETWEEN 6 AND 10) AS six_to_ten_collaterals,
        SUM(collateral_count > 10) AS more_than_ten_collaterals
    FROM (
        SELECT COUNT(DISTINCT CONCAT(doctor_number, '-', collateral_id)) AS collateral_count
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

// Fetch unique (doctor_number, collateral_id) for that Brand_Campaign_ID for the last 7 days
$queryCollateralDistributionLast7Days = "
    SELECT 
        SUM(collateral_count = 1) AS one_collateral,
        SUM(collateral_count BETWEEN 2 AND 5) AS two_to_five_collaterals,
        SUM(collateral_count BETWEEN 6 AND 10) AS six_to_ten_collaterals,
        SUM(collateral_count > 10) AS more_than_ten_collaterals
    FROM (
        SELECT COUNT(DISTINCT CONCAT(doctor_number, '-', collateral_id)) AS collateral_count
        FROM collateral_transactions
        WHERE Brand_Campaign_ID = '$brand_campaign_id' 
          AND transaction_date >= DATE_SUB(NOW(), INTERVAL 7 DAY)
          AND comment NOT IN ('collateral viewed', 'Video Viewed', 'PDF Downloaded', 'PDF viewed')
        GROUP BY doctor_number
    ) AS doctor_collateral_counts_last_7_days";
$resultCollateralDistributionLast7Days = mysqli_query($conn, $queryCollateralDistributionLast7Days);

// Set defaults to 0 if no results are found
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

// Fetch the count of unique (doctor_number, collateral_id) for that Brand_Campaign_ID where viewed = 1
$queryDoctorEngagement = "
    SELECT 
        SUM(collateral_view_count = 1) AS one_collateral,
        SUM(collateral_view_count BETWEEN 2 AND 5) AS two_to_five_collaterals,
        SUM(collateral_view_count BETWEEN 6 AND 10) AS six_to_ten_collaterals,
        SUM(collateral_view_count > 10) AS more_than_ten_collaterals
    FROM (
        SELECT COUNT(DISTINCT CONCAT(doctor_number, '-', collateral_id)) AS collateral_view_count
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

// Fetch unique (doctor_number, collateral_id) for that Brand_Campaign_ID for the last 7 days where viewed = 1
$queryDoctorEngagementLast7Days = "
    SELECT 
    SUM(collateral_view_count = 1) AS one_collateral,
    SUM(collateral_view_count BETWEEN 2 AND 5) AS two_to_five_collaterals,
    SUM(collateral_view_count BETWEEN 6 AND 10) AS six_to_ten_collaterals,
    SUM(collateral_view_count > 10) AS more_than_ten_collaterals
FROM (
    SELECT COUNT(DISTINCT CONCAT(doctor_number, '-', collateral_id)) AS collateral_view_count
    FROM collateral_transactions
    WHERE Brand_Campaign_ID = '$brand_campaign_id' AND viewed = 1 
      AND transaction_date >= DATE_SUB(NOW(), INTERVAL 7 DAY)
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


mysqli_close($conn);
?>
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta http-equiv="X-UA-Compatible" content="IE=edge">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Report Format</title>
    <!-- Bootstrap CSS -->
    <link href="https://stackpath.bootstrapcdn.com/bootstrap/4.5.2/css/bootstrap.min.css" rel="stylesheet">
</head>
<style>
    .btn-container {
        display: flex;
        justify-content: start;
        gap: 10px;
        margin-bottom: 20px;
    }
</style>
<body>

<div class="container mt-5">
    <div class="btn-container">
        <a href="https://<?php echo $reports; ?>.<?php echo $cpd; ?>/reports/Zuventus/dashboard.php" class="btn btn-primary">Dashboard</a>
        <a href="https://<?php echo $reports; ?>.<?php echo $cpd; ?>/reports/Zuventus/download_csv.php?brand_campaign_id=<?php echo urlencode($brand_campaign_id); ?>" class="btn btn-success">Download CSV</a>
    </div>

    <!-- Field Rep Activity Section -->
    <div class="mb-4">
        <div class="bg-info text-white p-2 font-weight-bold">Field Rep Activity</div>
        <table class="table table-bordered">
            <thead class="thead-light">
                <tr>
                    <th>Field Rep Activity</th>
                    <th>Last 7 Days</th>
                    <th><?php echo htmlspecialchars($startDate) . " - " . htmlspecialchars($endDate); ?></th>
                </tr>
            </thead>
            <tbody>
                <tr>
                    <td>Total Number of Unique Field Reps Registered</td>
                    <td><?php echo $uniqueFieldRepsCountLast7Days; ?></td>
                    <td><?php echo $uniqueFieldRepsCount; ?></td>
                </tr>
                <tr>
                    <td>Total Number of Unique Doctors Registered</td>
                    <td><?php echo $uniqueDoctorsCountLast7Days; ?></td>
                    <td><?php echo $uniqueDoctorsCount; ?></td>
                </tr>
            </tbody>
        </table>
    </div>

    <!-- Collateral Distribution Section -->
    <div class="mb-4">
        <div class="bg-info text-white p-2 font-weight-bold">How many doctors have been sent any collateral at least once?</div>
        <table class="table table-bordered">
            <thead class="thead-light">
                <tr>
                    <th>Collaterals</th>
                    <th>Last 7 Days</th>
                    <th><?php echo htmlspecialchars($startDate) . " - " . htmlspecialchars($endDate); ?></th>
                </tr>
            </thead>
            <tbody>
                <tr>
                    <td>1 collateral</td>
                    <td><?php echo $oneCollateralCountLast7Days; ?></td>
                    <td><?php echo $oneCollateralCount; ?></td>
                </tr>
                <tr>
                    <td>2-5 collaterals</td>
                    <td><?php echo $twoToFiveCollateralsCountLast7Days; ?></td>
                    <td><?php echo $twoToFiveCollateralsCount; ?></td>
                </tr>
                <tr>
                    <td>6-10 collaterals</td>
                    <td><?php echo $sixToTenCollateralsCountLast7Days; ?></td>
                    <td><?php echo $sixToTenCollateralsCount; ?></td>
                </tr>
                <tr>
                    <td>More than 10 collaterals</td>
                    <td><?php echo $moreThanTenCollateralsCountLast7Days; ?></td>
                    <td><?php echo $moreThanTenCollateralsCount; ?></td>
                </tr>
            </tbody>
        </table>
    </div>
<!-- Doctor Engagement Activity Section -->
<div class="mb-4">
    <div class="bg-info text-white p-2 font-weight-bold">Doctor Engagement Activity</div>
    <table class="table table-bordered">
        <thead class="thead-light">
            <tr>
                <th>Number of doctors who have viewed any collateral?</th>
                <th>Last 7 Days</th>
                <th><?php echo htmlspecialchars($startDate) . " - " . htmlspecialchars($endDate); ?></th>
            </tr>
        </thead>
        <tbody>
            <tr>
                <td>1 collateral</td>
                <td><?php echo $oneCollateralViewedCountLast7Days; ?></td>
                <td><?php echo $oneCollateralViewedCount; ?></td>
            </tr>
            <tr>
                <td>2-5 collaterals</td>
                <td><?php echo $twoToFiveCollateralsViewedCountLast7Days; ?></td>
                <td><?php echo $twoToFiveCollateralsViewedCount; ?></td>
            </tr>
            <tr>
                <td>6-10 collaterals</td>
                <td><?php echo $sixToTenCollateralsViewedCountLast7Days; ?></td>
                <td><?php echo $sixToTenCollateralsViewedCount; ?></td>
            </tr>
            <tr>
                <td>More than 10 collaterals</td>
                <td><?php echo $moreThanTenCollateralsViewedCountLast7Days; ?></td>
                <td><?php echo $moreThanTenCollateralsViewedCount; ?></td>
            </tr>
        </tbody>
    </table>
</div>


</div>

<!-- Bootstrap JS and dependencies -->
<script src="https://code.jquery.com/jquery-3.5.1.slim.min.js"></script>
<script src="https://cdn.jsdelivr.net/npm/@popperjs/core@2.9.3/dist/umd/popper.min.js"></script>
<script src="https://stackpath.bootstrapcdn.com/bootstrap/4.5.2/js/bootstrap.min.js"></script>
</body>
</html>
