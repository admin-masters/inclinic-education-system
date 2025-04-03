<?php
error_reporting(E_ALL);
ini_set('display_errors', 1);
require 'config/constants.php'; // connection file

$brand_campaign_id = isset($_GET['brand_campaign_id']) ? $_GET['brand_campaign_id'] : '';

// Fetch unique field_ids from the field_reps table
$sql = "SELECT DISTINCT field_id FROM field_reps WHERE brand_campaign_id = ?";
$stmt = $conn->prepare($sql);
$stmt->bind_param("s", $brand_campaign_id);
$stmt->execute();
$result = $stmt->get_result();

$field_reps = [];
if ($result->num_rows > 0) {
    while ($row = $result->fetch_assoc()) {
        $field_reps[] = $row;
    }
}
$stmt->close();

// Initialize an array to hold counts for each field_id
$recruitment_counts = [];
$total_unique_doctors = 0;
$total_same_doctors = 0;

foreach ($field_reps as $field_rep) {
    $recruitment_counts[$field_rep['field_id']] = ['unique_doctors' => 0, 'same_doctors' => 0];
}

// Fetch all doctors for the given brand campaign
$sql = "SELECT id, mobile_number, field_id FROM doctors WHERE Brand_Campaign_ID = ? ORDER BY id ASC";
$stmt = $conn->prepare($sql);
$stmt->bind_param("s", $brand_campaign_id);
$stmt->execute();
$result = $stmt->get_result();

$recruited_doctors = [];
while ($row = $result->fetch_assoc()) {
    $mobile_number = $row['mobile_number'];
    $field_id = $row['field_id'];
    $doctor_id = $row['id'];

    // If this is the first time the doctor is being counted
    if (!isset($recruited_doctors[$mobile_number])) {
        $recruited_doctors[$mobile_number] = $field_id;
        $recruitment_counts[$field_id]['unique_doctors']++;
        $total_unique_doctors++;
    } else {
        // Doctor has already been recruited by another field rep
        $first_field_id = $recruited_doctors[$mobile_number];
        $recruitment_counts[$field_id]['same_doctors']++;
        $total_same_doctors++;
        
        // Update the same_doctors link with the doctor's ID
        $recruitment_counts[$field_id]['same_doctors_link'] = "<a href='collateral_details.php?doctor_id={$doctor_id}&field_id={$field_id}&brand_campaign_id={$brand_campaign_id}'>{$recruitment_counts[$field_id]['same_doctors']}</a>";
    }
}

$stmt->close();

// Initialize counters for the third table
$collateral_counts = [
    '1_received' => 0, '1_viewed' => 0,
    '2_5_received' => 0, '2_5_viewed' => 0,
    '6_10_received' => 0, '6_10_viewed' => 0,
    '11_plus_received' => 0, '11_plus_viewed' => 0,
];

// Fetch collateral data for the third table
$sql = "
    SELECT doctor_number, COUNT(DISTINCT collateral_id) as collateral_count, 
           COUNT(DISTINCT CASE WHEN viewed = 1 THEN collateral_id END) as viewed_count 
    FROM collateral_transactions 
    WHERE Brand_Campaign_ID = ? 
    GROUP BY doctor_number";
$stmt = $conn->prepare($sql);
$stmt->bind_param("s", $brand_campaign_id);
$stmt->execute();
$result = $stmt->get_result();

while ($row = $result->fetch_assoc()) {
    $collateral_count = $row['collateral_count'];
    $viewed_count = $row['viewed_count'];

    // Count received collaterals
    if ($collateral_count == 1) {
        $collateral_counts['1_received']++;
    } elseif ($collateral_count >= 2 && $collateral_count <= 5) {
        $collateral_counts['2_5_received']++;
    } elseif ($collateral_count >= 6 && $collateral_count <= 10) {
        $collateral_counts['6_10_received']++;
    } elseif ($collateral_count >= 11) {
        $collateral_counts['11_plus_received']++;
    }

    // Count viewed collaterals
    if ($viewed_count == 1) {
        $collateral_counts['1_viewed']++;
    } elseif ($viewed_count >= 2 && $viewed_count <= 5) {
        $collateral_counts['2_5_viewed']++;
    } elseif ($viewed_count >= 6 && $viewed_count <= 10) {
        $collateral_counts['6_10_viewed']++;
    } elseif ($viewed_count >= 11) {
        $collateral_counts['11_plus_viewed']++;
    }
}

$stmt->close();

// Fetch distinct collateral IDs for the given brand campaign
$sql = "SELECT DISTINCT collateral_id FROM collateral_transactions WHERE Brand_Campaign_ID = ?";
$stmt = $conn->prepare($sql);
$stmt->bind_param("s", $brand_campaign_id);
$stmt->execute();
$result = $stmt->get_result();

$collateral_ids = [];
while ($row = $result->fetch_assoc()) {
    $collateral_ids[] = $row['collateral_id'];
}
$stmt->close();

// Do not close the connection before using it for the final queries
?>

<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Report</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
    <style>
        .table-custom {
            margin: 20px auto;
            width: 95%;
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
        .table-custom .total-row th, .table-custom .total-row td {
            background-color: #e9ecef;
            font-weight: bold;
        }
        .yellow-background {
            background-color: yellow;
        }
    </style>
</head>
<body>
    <div class="container">
        <h2 class="text-center mt-5">Campaign Report</h2>
        

        <!-- Second Table -->
        <table class="table table-bordered table-custom mt-4">
    <thead>
        <tr>
            <th>Field Rep Ids</th>
            <th>Number of Doctors Recruited by Field Rep</th>
            <th>Number of Same Doctors Recruited by Field Rep</th>
        </tr>
    </thead>
    <tbody>
        <?php
        foreach ($recruitment_counts as $field_id => $counts) {
            echo "<tr>";
            echo "<td>{$field_id}</td>";
            echo "<td>{$counts['unique_doctors']}</td>";
            // Remove the link from the "same_doctors" cell
            echo "<td>{$counts['same_doctors']}</td>";
            echo "</tr>";
        }
        ?>
        <!-- Total Row -->
        <tr class="total-row">
            <td>Total</td>
            <td><?php echo $total_unique_doctors; ?></td>
            <!-- Add the link to the total same doctors count -->
            <td><a href="collateral_details.php?brand_campaign_id=<?php echo $brand_campaign_id; ?>"><?php echo $total_same_doctors; ?></a></td>
        </tr>
    </tbody>
</table>

        <!-- Third Table -->
        <table class="table table-bordered table-custom mt-4">
            <thead>
                <tr>
                    <th>No. of Doctors Received 1 Collateral</th>
                    <th>No. of Doctors Viewed 1 Collateral</th>
                    <th>No. of Doctors Received 2 - 5 Collaterals</th>
                    <th>No. of Doctors Viewed 2 - 5 Collaterals</th>
                    <th>No. of Doctors Received 6 - 10 Collaterals</th>
                    <th>No. of Doctors Viewed 6 - 10 Collaterals</th>
                    <th>No. of Doctors Received 11 - >11 Collaterals</th>
                    <th>No. of Doctors Viewed 11 - >11 Collaterals</th>
                </tr>
            </thead>
            <tbody>
                <tr>
                    <td><?php echo $collateral_counts['1_received']; ?></td>
                    <td><?php echo $collateral_counts['1_viewed']; ?></td>
                    <td><?php echo $collateral_counts['2_5_received']; ?></td>
                    <td><?php echo $collateral_counts['2_5_viewed']; ?></td>
                    <td><?php echo $collateral_counts['6_10_received']; ?></td>
                    <td><?php echo $collateral_counts['6_10_viewed']; ?></td>
                    <td><?php echo $collateral_counts['11_plus_received']; ?></td>
                    <td><?php echo $collateral_counts['11_plus_viewed']; ?></td>
                </tr>
            </tbody>
        </table>

        <!-- Collateral-wise Analytics Table -->
        <div class="table-container table-responsive">
            <?php foreach ($collateral_ids as $collateral_id): ?>
                <h2>Collateral ID <?php echo $collateral_id; ?></h2>
                <table class="table table-bordered table-striped">
                    <thead>
                        <tr class="yellow-background">
                            <th>Date (Ascending Order)</th>
                            <th>Field rep ID</th>
                            <th>Doctor Name</th>
                            <th>Doctor Phone Number</th>
                            <th>Collateral Viewed (Yes/No)</th>
                            <th>PDF Viewed (Yes/No)</th>
                            <th>Video Viewed 100% (Yes/No)</th>
                        </tr>
                    </thead>
                    <tbody>
                        <?php
                        $collateral_details_query = "
                            SELECT 
                                DATE(transaction_date) as transaction_date, 
                                field_id, 
                                doctor_name, 
                                doctor_number,
                                CASE WHEN viewed > 0 THEN 'Yes' ELSE 'No' END as collateral_viewed,
                                CASE WHEN pdf_page = 1 THEN 'Yes' ELSE 'No' END as pdf_viewed,
                                CASE WHEN video_pec = 3 THEN 'Yes' ELSE 'No' END as video_viewed
                            FROM collateral_transactions
                            WHERE Brand_Campaign_ID = ? AND collateral_id = ?
                            ORDER BY transaction_date ASC";
                        
                        $collateral_details_stmt = $conn->prepare($collateral_details_query);
                        $collateral_details_stmt->bind_param("ss", $brand_campaign_id, $collateral_id);
                        $collateral_details_stmt->execute();
                        $collateral_details_result = $collateral_details_stmt->get_result();
                        
                        while ($row = $collateral_details_result->fetch_assoc()): ?>
                            <tr>
                                <td><?php echo $row['transaction_date']; ?></td>
                                <td><?php echo $row['field_id']; ?></td>
                                <td><?php echo $row['doctor_name']; ?></td>
                                <td><?php echo $row['doctor_number']; ?></td>
                                <td><?php echo $row['collateral_viewed']; ?></td>
                                <td><?php echo $row['pdf_viewed']; ?></td>
                                <td><?php echo $row['video_viewed']; ?></td>
                            </tr>
                        <?php endwhile; ?>
                    </tbody>
                </table>
            <?php endforeach; ?>
        </div>
    </div>

    <?php $conn->close(); // Close the connection at the very end after everything is done ?>

    <div class="text-center mt-4">
    <button type="button" class="btn btn-primary btn-lg" 
            onclick="window.location.href='collateral_sharing_report.php?brand_campaign_id=<?php echo $brand_campaign_id; ?>'">
        1
    </button>
    <button type="button" class="btn btn-secondary btn-lg" 
            onclick="window.location.href='collateral_sharing_report_1.php?brand_campaign_id=<?php echo $brand_campaign_id; ?>'">
        2
    </button>
</div>

    <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/js/bootstrap.bundle.min.js"></script>
</body>
</html>
