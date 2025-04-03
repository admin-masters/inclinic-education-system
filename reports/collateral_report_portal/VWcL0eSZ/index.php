<?php
ini_set('display_errors', 1);
ini_set('display_startup_errors', 1);
include '../../config/constants.php'; 

$brand_campaign_id = isset($_GET['brand_campaign_id']) ? $_GET['brand_campaign_id'] : '';
$start_date = isset($_GET['start_date']) ? $_GET['start_date'] : '';
$end_date = isset($_GET['end_date']) ? $_GET['end_date'] : '';

$field_reps_data = [];
$total_last_7_days_count = 0;
$total_cumulative_count = 0;
$total_field_id_count = 0;

// If the brand_campaign_id is set, proceed with the query
if ($brand_campaign_id !== '') {
    // Prepare the SQL query to fetch field_ids without date filtering on field_reps
    $query = "SELECT DISTINCT field_id FROM field_reps WHERE brand_campaign_id = ?";

    // Use prepared statements to prevent SQL injection
    $stmt = $conn->prepare($query);

    if (!$stmt) {
        die("Prepare failed: (" . $conn->errno . ") " . $conn->error);
    }

    $stmt->bind_param("s", $brand_campaign_id);

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
        if (!$stmt_last_7_days) {
            die("Prepare failed: (" . $conn->errno . ") " . $conn->error);
        }
        $stmt_last_7_days->bind_param("ss", $field_id, $brand_campaign_id);
        $stmt_last_7_days->execute();
        $result_last_7_days = $stmt_last_7_days->get_result();
        $last_7_days_count = $result_last_7_days->fetch_assoc()['last_7_days_count'];

        // Get the cumulative count
        if ($start_date && $end_date) {
            $stmt_cumulative = $conn->prepare($cumulative_count_query);
            if (!$stmt_cumulative) {
                die("Prepare failed: (" . $conn->errno . ") " . $conn->error);
            }
            $stmt_cumulative->bind_param("ssss", $field_id, $brand_campaign_id, $start_date, $end_date);
        } else {
            $stmt_cumulative = $conn->prepare($cumulative_count_query);
            if (!$stmt_cumulative) {
                die("Prepare failed: (" . $conn->errno . ") " . $conn->error);
            }
            $stmt_cumulative->bind_param("ss", $field_id, $brand_campaign_id);
        }

        $stmt_cumulative->execute();
        $result_cumulative = $stmt_cumulative->get_result();
        $cumulative_count = $result_cumulative->fetch_assoc()['cumulative_count'];

        // Determine the region using the CSV mapping
        $region = isset($region_map[$field_id]) ? $region_map[$field_id] : '-';

        // Store the fetched data in an associative array
        $field_reps_data[] = [
            'field_id' => $field_id,
            'last_7_days_count' => $last_7_days_count,
            'cumulative_count' => $cumulative_count,
            'region' => $region
        ];

        // Add counts to the total
        $total_last_7_days_count += $last_7_days_count;
        $total_cumulative_count += $cumulative_count;
        $total_field_id_count++; // Increment the total Field ID count

        // Free results and close statements
        $stmt_last_7_days->close();
        $stmt_cumulative->close();
    }

    // Free result and close statement
    $stmt->close();
}
?>

<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Field ID Data</title>
    <link href="https://stackpath.bootstrapcdn.com/bootstrap/4.5.2/css/bootstrap.min.css" rel="stylesheet">
    <style>
        .btn-container {
            display: flex;
            justify-content: start;
            gap: 10px;
            margin-bottom: 20px;
        }
    </style>
</head>
<body>
    <div class="container mt-5">
        <div class="btn-container">
            <a href="https://<?php echo $reports; ?>.<?php echo $cpd; ?>/reports/collateral_report_portal/dashboard.php" class="btn btn-primary">Dashboard</a>
            <a href="https://<?php echo $reports; ?>.<?php echo $cpd; ?>/reports/collateral_report_portal/PDF/index.php?start_date=<?php echo urlencode($start_date); ?>&end_date=<?php echo urlencode($end_date); ?>&brand_campaign_id=<?php echo urlencode($brand_campaign_id); ?>" class="btn btn-danger">Download PDF</a>
            <a href="download_csv.php?start_date=<?php echo urlencode($start_date); ?>&end_date=<?php echo urlencode($end_date); ?>&brand_campaign_id=<?php echo urlencode($brand_campaign_id); ?>" class="btn btn-success">Download CSV</a>
            <a href="https://<?php echo $reports; ?>.<?php echo $cpd; ?>/reports/collateral_report_portal/common_report.php?brand_campaign_id=<?php echo urlencode($brand_campaign_id); ?>" class="btn btn-warning">Cumulative</a>
            <a href="https://<?php echo $reports; ?>.<?php echo $cpd; ?>/reports/collateral_report_portal/VWcL0eSZ/collateral_details.php?brand_campaign_id=<?php echo urlencode($brand_campaign_id); ?>" class="btn btn-light">Collateral Details</a>

        </div>

        <!-- Filter Form -->
        <form method="GET" action="">
            <input type="hidden" name="brand_campaign_id" value="<?php echo htmlspecialchars($brand_campaign_id); ?>">
            <div class="form-row">
                <div class="form-group col-md-3">
                    <label for="start_date">Start Date</label>
                    <input type="date" class="form-control" name="start_date" id="start_date" value="<?php echo htmlspecialchars($start_date); ?>">
                </div>
                <div class="form-group col-md-3">
                    <label for="end_date">End Date</label>
                    <input type="date" class="form-control" name="end_date" id="end_date" value="<?php echo htmlspecialchars($end_date); ?>">
                </div>
                <div class="form-group col-md-3 align-self-end">
                    <button type="submit" class="btn btn-primary">Filter</button>
                </div>
            </div>
        </form>

        <h2 class="mb-4">Field ID Data</h2>
        <table class="table table-bordered">
            <thead class="thead-dark">
                <tr>
                    <th scope="col">Field ID</th>
                    <th scope="col">Last 7 Days Count</th>
                    <th scope="col">Cumulative</th>
                </tr>
            </thead>
            <tbody>
                <?php if (!empty($field_reps_data)): ?>
                    <?php foreach ($field_reps_data as $rep): ?>
                        <tr>
                            <td><?php echo htmlspecialchars($rep['field_id']); ?></td>
                            <td><?php echo htmlspecialchars($rep['last_7_days_count']); ?></td>
                            <td><?php echo htmlspecialchars($rep['cumulative_count']); ?></td>
                        </tr>
                    <?php endforeach; ?>
                    <!-- Total row -->
                    <tr>
                        <td><strong>Total Field IDs: <?php echo htmlspecialchars($total_field_id_count); ?></strong></td>
                        <td><strong><?php echo htmlspecialchars($total_last_7_days_count); ?></strong></td>
                        <td><strong><?php echo htmlspecialchars($total_cumulative_count); ?></strong></td>
                    </tr>
                <?php else: ?>
                    <tr>
                        <td colspan="3">No data available</td>
                    </tr>
                <?php endif; ?>
            </tbody>
        </table>
    </div>

    <script src="https://code.jquery.com/jquery-3.5.1.slim.min.js"></script>
    <script src="https://cdn.jsdelivr.net/npm/@popperjs/core@2.9.2/dist/umd/popper.min.js"></script>
    <script src="https://stackpath.bootstrapcdn.com/bootstrap/4.5.2/js/bootstrap.min.js"></script>
</body>
</html>
