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

$brand_campaign_id = 'FXJpcN7K'; // Replace with your desired brand_campaign_id

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

// Fetch doctor_number count for collateral_id 272
$queryCollateral272 = "SELECT COUNT(DISTINCT doctor_number) AS collateral_272_count FROM collateral_transactions WHERE collateral_id = 272 AND Brand_Campaign_ID = '$brand_campaign_id'";
$resultCollateral272 = mysqli_query($conn, $queryCollateral272);
$collateral272Count = ($resultCollateral272 && mysqli_num_rows($resultCollateral272) > 0) ? mysqli_fetch_assoc($resultCollateral272)['collateral_272_count'] : 0;

// Fetch doctor_number count for collateral_id 276
$queryCollateral276 = "SELECT COUNT(DISTINCT doctor_number) AS collateral_276_count FROM collateral_transactions WHERE collateral_id = 276 AND Brand_Campaign_ID = '$brand_campaign_id'";
$resultCollateral276 = mysqli_query($conn, $queryCollateral276);
$collateral276Count = ($resultCollateral276 && mysqli_num_rows($resultCollateral276) > 0) ? mysqli_fetch_assoc($resultCollateral276)['collateral_276_count'] : 0;

$queryCollateral273 = "SELECT COUNT(DISTINCT doctor_number) AS collateral_273_count FROM collateral_transactions WHERE collateral_id = 273 AND Brand_Campaign_ID = '$brand_campaign_id'";
$resultCollateral273 = mysqli_query($conn, $queryCollateral273);
$collateral273Count = ($resultCollateral273 && mysqli_num_rows($resultCollateral273) > 0) ? mysqli_fetch_assoc($resultCollateral273)['collateral_273_count'] : 0;

$queryCollateral277 = "SELECT COUNT(DISTINCT doctor_number) AS collateral_277_count FROM collateral_transactions WHERE collateral_id = 277 AND Brand_Campaign_ID = '$brand_campaign_id'";
$resultCollateral277 = mysqli_query($conn, $queryCollateral277);
$collateral277Count = ($resultCollateral277 && mysqli_num_rows($resultCollateral277) > 0) ? mysqli_fetch_assoc($resultCollateral277)['collateral_277_count'] : 0;

$queryCollateral274 = "SELECT COUNT(DISTINCT doctor_number) AS collateral_274_count FROM collateral_transactions WHERE collateral_id = 274 AND Brand_Campaign_ID = '$brand_campaign_id'";
$resultCollateral274 = mysqli_query($conn, $queryCollateral274);
$collateral274Count = ($resultCollateral274 && mysqli_num_rows($resultCollateral274) > 0) ? mysqli_fetch_assoc($resultCollateral274)['collateral_274_count'] : 0;

$queryCollateral421 = "SELECT COUNT(DISTINCT doctor_number) AS collateral_421_count FROM collateral_transactions WHERE collateral_id = 421 AND Brand_Campaign_ID = '$brand_campaign_id'";
$resultCollateral421 = mysqli_query($conn, $queryCollateral421);
$collateral421Count = ($resultCollateral421 && mysqli_num_rows($resultCollateral421) > 0) ? mysqli_fetch_assoc($resultCollateral421)['collateral_421_count'] : 0;


// Fetch the sum of 'viewed' for collateral_id 272
$queryViewed272 = "SELECT SUM(viewed) AS collateral_272_viewed FROM collateral_transactions WHERE collateral_id = 272 AND Brand_Campaign_ID = '$brand_campaign_id'";
$resultViewed272 = mysqli_query($conn, $queryViewed272);
$collateral272Viewed = ($resultViewed272 && mysqli_num_rows($resultViewed272) > 0) ? mysqli_fetch_assoc($resultViewed272)['collateral_272_viewed'] : 0;

// Fetch the sum of 'viewed' for collateral_id 276
$queryViewed276 = "SELECT SUM(viewed) AS collateral_276_viewed FROM collateral_transactions WHERE collateral_id = 276 AND Brand_Campaign_ID = '$brand_campaign_id'";
$resultViewed276 = mysqli_query($conn, $queryViewed276);
$collateral276Viewed = ($resultViewed276 && mysqli_num_rows($resultViewed276) > 0) ? mysqli_fetch_assoc($resultViewed276)['collateral_276_viewed'] : 0;

$queryViewed273 = "SELECT SUM(viewed) AS collateral_273_viewed FROM collateral_transactions WHERE collateral_id = 273 AND Brand_Campaign_ID = '$brand_campaign_id'";
$resultViewed273 = mysqli_query($conn, $queryViewed273);
$collateral273Viewed = ($resultViewed273 && mysqli_num_rows($resultViewed273) > 0) ? mysqli_fetch_assoc($resultViewed273)['collateral_273_viewed'] : 0;

$queryViewed277 = "SELECT SUM(viewed) AS collateral_277_viewed FROM collateral_transactions WHERE collateral_id = 277 AND Brand_Campaign_ID = '$brand_campaign_id'";
$resultViewed277 = mysqli_query($conn, $queryViewed277);
$collateral277Viewed = ($resultViewed277 && mysqli_num_rows($resultViewed277) > 0) ? mysqli_fetch_assoc($resultViewed277)['collateral_277_viewed'] : 0;

$queryViewed274 = "SELECT SUM(viewed) AS collateral_274_viewed FROM collateral_transactions WHERE collateral_id = 274 AND Brand_Campaign_ID = '$brand_campaign_id'";
$resultViewed274 = mysqli_query($conn, $queryViewed274);
$collateral274Viewed = ($resultViewed274 && mysqli_num_rows($resultViewed274) > 0) ? mysqli_fetch_assoc($resultViewed274)['collateral_274_viewed'] : 0;

$queryViewed421 = "SELECT SUM(viewed) AS collateral_421_viewed FROM collateral_transactions WHERE collateral_id = 421 AND Brand_Campaign_ID = '$brand_campaign_id'";
$resultViewed421 = mysqli_query($conn, $queryViewed421);
$collateral421Viewed = ($resultViewed421 && mysqli_num_rows($resultViewed421) > 0) ? mysqli_fetch_assoc($resultViewed421)['collateral_421_viewed'] : 0;


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
        <a href="https://<?php echo $reports; ?>.<?php echo $cpd; ?>/reports/FXJpcN7K/FXJpcN7K/index.php?brand_campaign_id=<?php echo urlencode($brand_campaign_id); ?>" class="btn btn-primary">Back</a>
        <a href="https://<?php echo $reports; ?>.<?php echo $cpd; ?>/reports/FXJpcN7K/download_csv.php?brand_campaign_id=<?php echo urlencode($brand_campaign_id); ?>" class="btn btn-success">Download CSV</a>
    </div>

    <!-- Field Rep Activity Section -->
    <div class="mb-4">
        <div class="bg-info text-white p-2 font-weight-bold">Field Rep Activity</div>
        <table class="table table-bordered">
            <thead class="thead-light">
                <tr>
                    <th>Field Rep Activity</th>
                    <th><?php echo htmlspecialchars($startDate) . " - " . htmlspecialchars($endDate); ?></th>
                </tr>
            </thead>
            <tbody>
                <tr>
                    <td>Total Number of Unique Field Reps Registered</td>
                    <td><?php echo $uniqueFieldRepsCount; ?></td>
                </tr>
                <tr>
                    <td>Total Number of Unique Doctors Registered</td>
                    <td><?php echo $uniqueDoctorsCount; ?></td>
                </tr>
            </tbody>
        </table>
    </div>
    <div class="mb-4">
        <div class="bg-info text-white p-2 font-weight-bold">Collateral Activity</div>
        <table class="table table-bordered">
            <thead class="thead-light">
                <tr>
                    <th>Collateral Name</th>
                    <th>Number of doctors who have received the collateral <?php echo htmlspecialchars($startDate) . " - " . htmlspecialchars($endDate); ?></th>
                    <th>Number of doctors who have viewed collateral <?php echo htmlspecialchars($startDate) . " - " . htmlspecialchars($endDate); ?></th>
                </tr>
            </thead>
            <tbody>
    <tr>
        <td>Mini CME 1 Managing High-Volume Pediatric Diarrhoea</td>
        <td><?php echo $collateral272Count; ?></td>
        <td><?php echo $collateral272Viewed; ?></td> <!-- Display sum of viewed for collateral 272 -->
    </tr>
    <tr>
        <td>Case Study on conditions linked to diarrhea and nutrition - Issue 1</td>
        <td><?php echo $collateral276Count; ?></td>
        <td><?php echo $collateral276Viewed; ?></td> <!-- Display sum of viewed for collateral 276 -->
    </tr>
    <tr>
        <td>Mini CME Issue 2 on Understanding Diarrhoea and the Role of Antibiotics in Children</td>
        <td><?php echo $collateral273Count; ?></td>
        <td><?php echo $collateral273Viewed; ?></td> <!-- Display sum of viewed for collateral 276 -->
    </tr>
    <tr>
        <td>Case Study Issue 2 on conditions related to diarrhoea & nutrition</td>
        <td><?php echo $collateral277Count; ?></td>
        <td><?php echo $collateral277Viewed; ?></td> <!-- Display sum of viewed for collateral 276 -->
    </tr>
    <tr>
        <td>Mini CME Issue 3 Blood and Mucus in Pediatric Stools: Causes and Concerns</td>
        <td><?php echo $collateral274Count; ?></td>
        <td><?php echo $collateral274Viewed; ?></td> <!-- Display sum of viewed for collateral 276 -->
    </tr>
    <tr>
        <td>Case Study Issue 3 on conditions related to diarrhoea & nutrition</td>
        <td><?php echo $collateral421Count; ?></td>
        <td><?php echo $collateral421Viewed; ?></td> <!-- Display sum of viewed for collateral 276 -->
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
