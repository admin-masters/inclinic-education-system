<?php
ini_set('display_errors', 1);
ini_set('display_startup_errors', 1);
include '../../config/constants.php';
$brand_campaign_id = isset($_GET['brand_campaign_id']) ? $_GET['brand_campaign_id'] : '';
// Set the number of results to display per page
$results_per_page = 500;

// Find out the number of results stored in the database
$sql_count = "SELECT COUNT(*) AS total FROM wallace";
$result_count = $conn->query($sql_count);
$row_count = $result_count->fetch_assoc();
$total_results = $row_count['total'];

// Determine the total number of pages available
$total_pages = ceil($total_results / $results_per_page);

// Find out which page number visitor is currently on
$page = isset($_GET['page']) ? (int)$_GET['page'] : 1;
if ($page > $total_pages) {
    $page = $total_pages;
}
if ($page < 1) {
    $page = 1;
}

// Determine the SQL LIMIT starting number for the results on the displaying page
$start_from = ($page - 1) * $results_per_page;

// SQL query to fetch data with pagination
$sql = "
    SELECT 
        w.zone, w.region, w.area, w.field_id, w.doctor_id, w.doctor_name, w.doctor_number,
        MAX(CASE WHEN ct.collateral_id = 272 THEN 1 ELSE 0 END) AS collateral_272,
        MAX(CASE WHEN ct.collateral_id = 272 AND ct.viewed = 1 THEN 1 ELSE 0 END) AS viewed_272,
        MAX(CASE WHEN ct.collateral_id = 276 THEN 1 ELSE 0 END) AS collateral_276,
        MAX(CASE WHEN ct.collateral_id = 276 AND ct.viewed = 1 THEN 1 ELSE 0 END) AS viewed_276,
        MAX(CASE WHEN ct.collateral_id = 273 THEN 1 ELSE 0 END) AS collateral_273,
        MAX(CASE WHEN ct.collateral_id = 273 AND ct.viewed = 1 THEN 1 ELSE 0 END) AS viewed_273,
        MAX(CASE WHEN ct.collateral_id = 277 THEN 1 ELSE 0 END) AS collateral_277,
        MAX(CASE WHEN ct.collateral_id = 277 AND ct.viewed = 1 THEN 1 ELSE 0 END) AS viewed_277,
        MAX(CASE WHEN ct.collateral_id = 397 THEN 1 ELSE 0 END) AS collateral_397,
        MAX(CASE WHEN ct.collateral_id = 397 AND ct.viewed = 1 THEN 1 ELSE 0 END) AS viewed_397
    FROM wallace w
    LEFT JOIN collateral_transactions ct 
        ON w.field_id = ct.field_id AND w.doctor_number = ct.doctor_number
    GROUP BY w.zone, w.region, w.area, w.field_id, w.doctor_id, w.doctor_name, w.doctor_number
    LIMIT $start_from, $results_per_page
";
$result = $conn->query($sql);
?>

<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Field ID Data</title>
    <link href="https://stackpath.bootstrapcdn.com/bootstrap/4.5.2/css/bootstrap.min.css" rel="stylesheet">
    <style>
        .pagination {
            margin-top: 5px;
            justify-content: center;
        }
        .table-responsive {
            max-width: 100%;
            max-height: 700px;
            overflow-y: auto;
        }
        .btn-container {
            display: flex;
            justify-content: start;
            gap: 10px;
            margin-bottom: 20px;
        }
    </style>
</head>
<body>
    <div class="container-fluid mt-2 mx-auto">
        <!-- Buttons at the top -->
        <div class="btn-container">
            <a href="https://<?php echo $reports; ?>.<?php echo $cpd; ?>/reports/collateral_report_portal/dashboard.php" class="btn btn-primary">Dashboard</a>
            <a href="download_csv.php" class="btn btn-success">Download CSV</a>
            <a href="https://<?php echo $reports; ?>.<?php echo $cpd; ?>/reports/collateral_report_portal/common_report.php?brand_campaign_id=<?php echo urlencode($brand_campaign_id); ?>" class="btn btn-warning">Cumulative</a>
            <a href="https://<?php echo $reports; ?>.<?php echo $cpd; ?>/reports/collateral_report_portal/FXJpcN7K/index1.php?brand_campaign_id=<?php echo urlencode($brand_campaign_id); ?>" class="btn btn-danger">Wallace Data</a>
            <a href="https://<?php echo $reports; ?>.<?php echo $cpd; ?>/reports/collateral_report_portal/FXJpcN7K/collateral_details.php?brand_campaign_id=<?php echo urlencode($brand_campaign_id); ?>" class="btn btn-light">Collateral Details</a>
        </div>
        
        <h2 class="mb-4">Field ID Data</h2>
        <div class="table-responsive">
            <table class="table table-bordered table-striped">
                <thead class="thead-dark">
                    <tr>
                        <th>Zone</th>
                        <th>Region</th>
                        <th>Area</th>
                        <th>Field ID</th>
                        <th>DR ID</th>
                        <th>Doctor Name</th>
                        <th>Phone</th>
                        <th>Collateral ID 272</th>
                        <th>Viewed Collateral ID 272</th>
                        <th>Collateral ID 276</th>
                        <th>Viewed Collateral ID 276</th>
                        <th>Collateral ID 273</th>
                        <th>Viewed Collateral ID 273</th>
                        <th>Collateral ID 277</th>
                        <th>Viewed Collateral ID 277</th>
                        <th>Collateral ID 397</th>
                        <th>Viewed Collateral ID 397</th>
                    </tr>
                </thead>
                <tbody>
                    <?php
                    if ($result->num_rows > 0) {
                        // Output data of each row
                        while($row = $result->fetch_assoc()) {
                            echo "<tr>";
                            echo "<td>" . htmlspecialchars($row['zone']) . "</td>";
                            echo "<td>" . htmlspecialchars($row['region']) . "</td>";
                            echo "<td>" . htmlspecialchars($row['area']) . "</td>";
                            echo "<td>" . htmlspecialchars($row['field_id']) . "</td>";
                            echo "<td>" . htmlspecialchars($row['doctor_id']) . "</td>";
                            echo "<td>" . htmlspecialchars($row['doctor_name']) . "</td>";
                            echo "<td>" . htmlspecialchars($row['doctor_number']) . "</td>";
                            echo "<td>" . htmlspecialchars($row['collateral_272']) . "</td>";
                            echo "<td>" . htmlspecialchars($row['viewed_272']) . "</td>";
                            echo "<td>" . htmlspecialchars($row['collateral_276']) . "</td>";
                            echo "<td>" . htmlspecialchars($row['viewed_276']) . "</td>";
                            echo "<td>" . htmlspecialchars($row['collateral_273']) . "</td>";
                            echo "<td>" . htmlspecialchars($row['viewed_273']) . "</td>";
                            echo "<td>" . htmlspecialchars($row['collateral_277']) . "</td>";
                            echo "<td>" . htmlspecialchars($row['viewed_277']) . "</td>";
                            echo "<td>" . htmlspecialchars($row['collateral_397']) . "</td>";
                            echo "<td>" . htmlspecialchars($row['viewed_397']) . "</td>";
                            echo "</tr>";
                        }
                    } else {
                        echo "<tr><td colspan='11'>No records found</td></tr>";
                    }
                    ?>
                </tbody>
            </table>
        </div>

        <!-- Pagination controls -->
        <nav aria-label="Page navigation">
            <ul class="pagination">
                <?php
                if ($page > 1) {
                    echo "<li class='page-item'><a class='page-link' href='?page=" . ($page - 1) . "'>Previous</a></li>";
                }
                
                for ($i = 1; $i <= $total_pages; $i++) {
                    echo "<li class='page-item" . ($i == $page ? ' active' : '') . "'><a class='page-link' href='?page=$i'>$i</a></li>";
                }
                
                if ($page < $total_pages) {
                    echo "<li class='page-item'><a class='page-link' href='?page=" . ($page + 1) . "'>Next</a></li>";
                }
                ?>
            </ul>
        </nav>
    </div>

    <script src="https://code.jquery.com/jquery-3.5.1.slim.min.js"></script>
    <script src="https://cdn.jsdelivr.net/npm/@popperjs/core@2.9.3/dist/umd/popper.min.js"></script>
    <script src="https://stackpath.bootstrapcdn.com/bootstrap/4.5.2/js/bootstrap.min.js"></script>
</body>
</html>
