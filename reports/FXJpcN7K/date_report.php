<?php
error_reporting(E_ALL);
ini_set('display_errors', 1);
require '../config/constants.php';
$brand_campaign_id = $_GET['brand_campaign_id'];

$total_field_reps = 0;
$total_doctors = 0;

// Initialize variables for collateral counts
$total_received_1 = 0;
$total_viewed_1 = 0;
$total_received_2_5 = 0;
$total_viewed_2_5 = 0;
$total_received_6_10 = 0;
$total_viewed_6_10 = 0;
$total_received_11_plus = 0;
$total_viewed_11_plus = 0;

$total_viewed_pdf = 0;
$total_downloaded_pdf = 0;
$total_watched_video = 0;

// Check if the form has been submitted
if ($_SERVER['REQUEST_METHOD'] == 'POST') {
    $start_date = $_POST['start_date'];
    $end_date = $_POST['end_date'];

    // Fetch the total number of field reps registered between the specified dates
    $sql = "SELECT COUNT(DISTINCT field_id) as total_field_reps 
            FROM field_reps 
            WHERE brand_campaign_id = ? AND `date` BETWEEN ? AND ?";
    
    $stmt = $conn->prepare($sql);
    $stmt->bind_param("sss", $brand_campaign_id, $start_date, $end_date);
    $stmt->execute();
    $result = $stmt->get_result();

    if ($result->num_rows > 0) {
        $total_field_reps = $result->fetch_assoc()['total_field_reps'];
    }

    // Fetch the total number of doctors registered between the specified dates
    $sql = "SELECT COUNT(DISTINCT mobile_number) as total_doctors 
            FROM doctors 
            WHERE brand_campaign_id = ? AND `registration_date` BETWEEN ? AND ?";
    
    $stmt = $conn->prepare($sql);
    $stmt->bind_param("sss", $brand_campaign_id, $start_date, $end_date);
    $stmt->execute();
    $result = $stmt->get_result();

    if ($result->num_rows > 0) {
        $total_doctors = $result->fetch_assoc()['total_doctors'];
    }

    // Fetch collateral transactions for doctors within the specified dates
    $sql = "SELECT doctor_number, 
                   COUNT(DISTINCT collateral_id) as collateral_count, 
                   SUM(viewed) as viewed_count
            FROM collateral_transactions 
            WHERE brand_campaign_id = ? AND `transaction_date` BETWEEN ? AND ?
            GROUP BY doctor_number";
    
    $stmt = $conn->prepare($sql);
    $stmt->bind_param("sss", $brand_campaign_id, $start_date, $end_date);
    $stmt->execute();
    $result = $stmt->get_result();

    while ($row = $result->fetch_assoc()) {
        $collateral_count = $row['collateral_count'];
        $viewed_count = $row['viewed_count'];

        // Count doctors based on the number of collaterals received
        if ($collateral_count == 1) {
            $total_received_1++;
        } elseif ($collateral_count >= 2 && $collateral_count <= 5) {
            $total_received_2_5++;
        } elseif ($collateral_count >= 6 && $collateral_count <= 10) {
            $total_received_6_10++;
        } elseif ($collateral_count >= 11) {
            $total_received_11_plus++;
        }

        // Count doctors based on the number of collaterals viewed
        if ($viewed_count == 1) {
            $total_viewed_1++;
        } elseif ($viewed_count >= 2 && $viewed_count <= 5) {
            $total_viewed_2_5++;
        } elseif ($viewed_count >= 6 && $viewed_count <= 10) {
            $total_viewed_6_10++;
        } elseif ($viewed_count >= 11) {
            $total_viewed_11_plus++;
        }
    }

    // Fetch the total number of doctors who viewed the PDF
    $sql = "SELECT COUNT(DISTINCT doctor_number) as total_viewed_pdf 
            FROM collateral_transactions 
            WHERE brand_campaign_id = ? 
            AND pdf_page = 1 
            AND `transaction_date` BETWEEN ? AND ?";

    $stmt = $conn->prepare($sql);
    $stmt->bind_param("sss", $brand_campaign_id, $start_date, $end_date);
    $stmt->execute();
    $result = $stmt->get_result();

    if ($result->num_rows > 0) {
        $total_viewed_pdf = $result->fetch_assoc()['total_viewed_pdf'];
    }

    // Fetch the total number of doctors who downloaded the PDF
    $sql = "SELECT COUNT(DISTINCT doctor_number) as total_downloaded_pdf 
            FROM collateral_transactions 
            WHERE brand_campaign_id = ? 
            AND pdf_download = 1 
            AND `transaction_date` BETWEEN ? AND ?";

    $stmt = $conn->prepare($sql);
    $stmt->bind_param("sss", $brand_campaign_id, $start_date, $end_date);
    $stmt->execute();
    $result = $stmt->get_result();

    if ($result->num_rows > 0) {
        $total_downloaded_pdf = $result->fetch_assoc()['total_downloaded_pdf'];
    }

    // Fetch the total number of doctors who watched the video
    $sql = "SELECT COUNT(DISTINCT doctor_number) as total_watched_video 
            FROM collateral_transactions 
            WHERE brand_campaign_id = ? 
            AND video_pec = 3 
            AND `transaction_date` BETWEEN ? AND ?";

    $stmt = $conn->prepare($sql);
    $stmt->bind_param("sss", $brand_campaign_id, $start_date, $end_date);
    $stmt->execute();
    $result = $stmt->get_result();

    if ($result->num_rows > 0) {
        $total_watched_video = $result->fetch_assoc()['total_watched_video'];
    }
}
?>

<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Brand Collateral Report</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
    <style>
        .container {
            margin-top: 50px;
        }
        .table-custom {
            margin-top: 30px;
            width: 80%;
            margin-left: auto;
            margin-right: auto;
        }
        .table-custom th, .table-custom td {
            text-align: center;
            vertical-align: middle;
        }
        .table-custom th {
            background-color: #f8f9fa;
            font-weight: bold;
        }
        .table-custom td {
            background-color: #ffffff;
        }
        .form-group {
            margin-bottom: 15px;
        }
        .btn-custom {
            margin-top: 20px;
        }
    </style>
</head>
<body>
    <div class="container">
        <h2 class="text-center">Brand Collateral Report Summary</h2>
        <div class="container">    
            <form method="POST" action="">
                <div class="row">
                    <div class="col-md-6 form-group">
                        <label for="start_date">Start Date</label>
                        <input type="date" class="form-control" id="start_date" name="start_date" required>
                    </div>
                    <div class="col-md-6 form-group">
                        <label for="end_date">End Date</label>
                        <input type="date" class="form-control" id="end_date" name="end_date" required>
                    </div>
                </div>
                <div class="text-center">
                    <button type="submit" class="btn btn-primary btn-custom">Generate Report</button>
                </div>
                <div class="text-center my-2">
                    <!-- <a href="https://<?php echo $reports; ?>.<?php echo $cpd; ?>/reports/collateral_report_portal/dashboard.php" class="btn btn-primary">Dashboard</a> -->
                </div>
            </form>
        </div>

        <table class="table table-bordered table-custom">
            <thead>
                <tr>
                    <th>Required Data</th>
                    <th>Total Data</th>
                </tr>
            </thead>
            <tbody>
                <tr>
                    <td>Total Field Reps Registered</td>
                    <td><?php echo $total_field_reps; ?></td>
                </tr>
                <tr>
                    <td>Total Doctors Registered</td>
                    <td><?php echo $total_doctors; ?></td>
                </tr>
                <tr>
                    <td>Total Number of Doctors Received 1 Collateral</td>
                    <td><?php echo $total_received_1; ?></td>
                </tr>
                <tr>
                    <td>Total Number of Doctors Viewed 1 Collateral</td>
                    <td><?php echo $total_viewed_1; ?></td>
                </tr>
                <tr>
                    <td>Total Number of Doctors Received 2 - 5 Collaterals</td>
                    <td><?php echo $total_received_2_5; ?></td>
                </tr>
                <tr>
                    <td>Total Number of Doctors Viewed 2 - 5 Collaterals</td>
                    <td><?php echo $total_viewed_2_5; ?></td>
                </tr>
                <tr>
                    <td>Total Number of Doctors Received 6 - 10 Collaterals</td>
                    <td><?php echo $total_received_6_10; ?></td>
                </tr>
                <tr>
                    <td>Total Number of Doctors Viewed 6 - 10 Collaterals</td>
                    <td><?php echo $total_viewed_6_10; ?></td>
                </tr>
                <tr>
                    <td>Total Number of Doctors Received 11 - >11 Collaterals</td>
                    <td><?php echo $total_received_11_plus; ?></td>
                </tr>
                <tr>
                    <td>Total Number of Doctors Viewed 11 - >11 Collaterals</td>
                    <td><?php echo $total_viewed_11_plus; ?></td>
                </tr>
                <tr>
                    <td>Total Number of Doctors Viewed PDF</td>
                    <td><?php echo $total_viewed_pdf; ?></td>
                </tr>
                <tr>
                    <td>Total Number of Doctors Downloaded the PDF</td>
                    <td><?php echo $total_downloaded_pdf; ?></td>
                </tr>
                <tr>
                    <td>Total Number of Doctors Watched the Video</td>
                    <td><?php echo $total_watched_video; ?></td>
                </tr>
            </tbody>
        </table>
    </div>
    
    <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/js/bootstrap.bundle.min.js"></script>
</body>
</html>
