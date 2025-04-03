<?php
ini_set('display_errors', 1);
ini_set('display_startup_errors', 1);
include '../../config/constants.php'; // Ensure this file establishes the database connection correctly

$servername = '13.234.88.80';
$username = 'test_doctor_u';
$password = 'V.D@-6*CwL0dmMP0';
$dbname = 'test_doctor';

$conn_other = new mysqli($servername, $username, $password, $dbname);

if ($conn_other->connect_error) {

    die('Connection failed: ' . $conn_other->connect_error);
}

$brand_campaign_id = isset($_GET['brand_campaign_id']) ? $_GET['brand_campaign_id'] : '';
$csv_file = 'doctors_data.csv'; // Path to your CSV file

// Function to read CSV file and convert it into an associative array
function readCsvFile($csv_file) {
    $csv_data = array();
    if (($handle = fopen($csv_file, "r")) !== FALSE) {
        $headers = fgetcsv($handle, 1000, ","); // Get the headers
        while (($row = fgetcsv($handle, 1000, ",")) !== FALSE) {
            $csv_data[] = array_combine($headers, $row); // Combine headers with data
        }
        fclose($handle);
    }
    return $csv_data;
}

// Read CSV data
$csv_data = readCsvFile($csv_file);

// Pagination variables
$limit = 500; // Number of records per page
$page = isset($_GET['page']) ? $_GET['page'] : 1;
$offset = ($page - 1) * $limit;

// Modified SQL query with LIMIT for pagination
$sql = "
    SELECT 
        fr.field_id, 
        d.name AS doctor_name, 
        d.mobile_number AS phone 
    FROM field_reps fr 
    LEFT JOIN doctors d 
    ON fr.field_id = d.field_id 
    WHERE fr.brand_campaign_id = ?
    GROUP BY fr.field_id, d.mobile_number
    LIMIT ?, ?
";

// Prepare and bind
$stmt = $conn->prepare($sql);
$stmt->bind_param("sii", $brand_campaign_id, $offset, $limit);
$stmt->execute();
$result = $stmt->get_result();

// Get total number of records for pagination
$sql_count = "
    SELECT COUNT(DISTINCT fr.field_id, d.mobile_number) AS total 
    FROM field_reps fr 
    LEFT JOIN doctors d 
    ON fr.field_id = d.field_id 
    WHERE fr.brand_campaign_id = ?
";
$stmt_count = $conn->prepare($sql_count);
$stmt_count->bind_param("s", $brand_campaign_id);
$stmt_count->execute();
$result_count = $stmt_count->get_result();
$total_records = $result_count->fetch_assoc()['total'];
$total_pages = ceil($total_records / $limit);

$date_query = "SELECT start_date FROM brand_campaigns WHERE brand_campaign_id = ?";
$date_stmt = $conn_other->prepare($date_query);
$date_stmt->bind_param("s", $brand_campaign_id); // use "s" for string binding
$date_stmt->execute();
$date_result = $date_stmt->get_result();
$date_row = $date_result->fetch_assoc();
$start_date = $date_row['start_date'];
$end_date = date('Y-m-d');

// Close the date statement
$date_stmt->close();
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
            <a href="download_csv1.php?brand_campaign_id=<?php echo urlencode($brand_campaign_id); ?>" class="btn btn-success">Download CSV</a>
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
                    </tr>
                </thead>
                <tbody>
                    <?php while ($row = $result->fetch_assoc()): ?>
                        <?php 
                            // Find corresponding CSV data based on Field ID and Phone
                            $csv_row = array_filter($csv_data, function($csv_item) use ($row) {
                                return $csv_item['Field ID'] === $row['field_id'] && $csv_item['Phone'] === $row['phone'];
                            });

                            // Get the first match from the filtered result
                            $csv_row = reset($csv_row);

                            // Check for collateral presence in collateral_transactions table
                            $mobile_number = $row['phone'];

                            // Query to check for collateral_id 
                            $sql_check_272 = "SELECT COUNT(*) AS count FROM collateral_transactions WHERE doctor_number = ? AND collateral_id = 272";
                            $stmt_check_272 = $conn->prepare($sql_check_272);
                            $stmt_check_272->bind_param("s", $mobile_number);
                            $stmt_check_272->execute();
                            $result_check_272 = $stmt_check_272->get_result();
                            $row_check_272 = $result_check_272->fetch_assoc();
                            $collateral_272 = ($row_check_272['count'] > 0) ? '1' : '0';

                            // Query to check for collateral_id 
                            $sql_check_276 = "SELECT COUNT(*) AS count FROM collateral_transactions WHERE doctor_number = ? AND collateral_id = 276";
                            $stmt_check_276 = $conn->prepare($sql_check_276);
                            $stmt_check_276->bind_param("s", $mobile_number);
                            $stmt_check_276->execute();
                            $result_check_276 = $stmt_check_276->get_result();
                            $row_check_276 = $result_check_276->fetch_assoc();
                            $collateral_276 = ($row_check_276['count'] > 0) ? '1' : '0';

                            $sql_check_273 = "SELECT COUNT(*) AS count FROM collateral_transactions WHERE doctor_number = ? AND collateral_id = 273";
                            $stmt_check_273 = $conn->prepare($sql_check_273);
                            $stmt_check_273->bind_param("s", $mobile_number);
                            $stmt_check_273->execute();
                            $result_check_273 = $stmt_check_273->get_result();
                            $row_check_273 = $result_check_273->fetch_assoc();
                            $collateral_273 = ($row_check_273['count'] > 0) ? '1' : '0';

                            $sql_check_277 = "SELECT COUNT(*) AS count FROM collateral_transactions WHERE doctor_number = ? AND collateral_id = 277";
                            $stmt_check_277 = $conn->prepare($sql_check_277);
                            $stmt_check_277->bind_param("s", $mobile_number);
                            $stmt_check_277->execute();
                            $result_check_277 = $stmt_check_277->get_result();
                            $row_check_277 = $result_check_277->fetch_assoc();
                            $collateral_277 = ($row_check_277['count'] > 0) ? '1' : '0';

                            // Query to fetch viewed status for collateral_id 
                            $sql_viewed_272 = "SELECT viewed FROM collateral_transactions WHERE doctor_number = ? AND collateral_id = 272 LIMIT 1";
                            $stmt_viewed_272 = $conn->prepare($sql_viewed_272);
                            $stmt_viewed_272->bind_param("s", $mobile_number);
                            $stmt_viewed_272->execute();
                            $result_viewed_272 = $stmt_viewed_272->get_result();
                            $viewed_272 = ($result_viewed_272->num_rows > 0) ? $result_viewed_272->fetch_assoc()['viewed'] : '0';

                            // Query to fetch viewed status for collateral_id 
                            $sql_viewed_276 = "SELECT viewed FROM collateral_transactions WHERE doctor_number = ? AND collateral_id = 276 LIMIT 1";
                            $stmt_viewed_276 = $conn->prepare($sql_viewed_276);
                            $stmt_viewed_276->bind_param("s", $mobile_number);
                            $stmt_viewed_276->execute();
                            $result_viewed_276 = $stmt_viewed_276->get_result();
                            $viewed_276 = ($result_viewed_276->num_rows > 0) ? $result_viewed_276->fetch_assoc()['viewed'] : '0';

                            $sql_viewed_273 = "SELECT viewed FROM collateral_transactions WHERE doctor_number = ? AND collateral_id = 273 LIMIT 1";
                            $stmt_viewed_273 = $conn->prepare($sql_viewed_273);
                            $stmt_viewed_273->bind_param("s", $mobile_number);
                            $stmt_viewed_273->execute();
                            $result_viewed_273 = $stmt_viewed_273->get_result();
                            $viewed_273 = ($result_viewed_273->num_rows > 0) ? $result_viewed_273->fetch_assoc()['viewed'] : '0';

                            $sql_viewed_277 = "SELECT viewed FROM collateral_transactions WHERE doctor_number = ? AND collateral_id = 277 LIMIT 1";
                            $stmt_viewed_277 = $conn->prepare($sql_viewed_277);
                            $stmt_viewed_277->bind_param("s", $mobile_number);
                            $stmt_viewed_277->execute();
                            $result_viewed_277 = $stmt_viewed_277->get_result();
                            $viewed_277 = ($result_viewed_277->num_rows > 0) ? $result_viewed_277->fetch_assoc()['viewed'] : '0';
                        ?>
                        <tr>
                            <td><?php echo htmlspecialchars($csv_row['Zone'] ?? ''); ?></td>
                            <td><?php echo htmlspecialchars($csv_row['Region'] ?? ''); ?></td>
                            <td><?php echo htmlspecialchars($csv_row['Area'] ?? ''); ?></td>
                            <td><?php echo htmlspecialchars($row['field_id']); ?></td>
                            <td><?php echo htmlspecialchars($csv_row['DR ID'] ?? ''); ?></td>
                            <td><?php echo htmlspecialchars($row['doctor_name']); ?></td>
                            <td><?php echo htmlspecialchars($row['phone']); ?></td>
                            <td><?php echo $collateral_272; ?></td>
                            <td><?php echo $viewed_272; ?></td>
                            <td><?php echo $collateral_276; ?></td>
                            <td><?php echo $viewed_276; ?></td>
                            <td><?php echo $collateral_273; ?></td>
                            <td><?php echo $viewed_273; ?></td>
                            <td><?php echo $collateral_277; ?></td>
                            <td><?php echo $viewed_277; ?></td>
                        </tr>
                    <?php endwhile; ?>
                </tbody>
            </table>
        </div>

        <!-- Pagination controls -->
        <nav aria-label="Page navigation">
            <ul class="pagination">
                <?php for ($i = 1; $i <= $total_pages; $i++): ?>
                    <li class="page-item <?php echo ($i == $page) ? 'active' : ''; ?>">
                        <a class="page-link" href="?brand_campaign_id=<?php echo $brand_campaign_id; ?>&page=<?php echo $i; ?>"><?php echo $i; ?></a>
                    </li>
                <?php endfor; ?>
            </ul>
        </nav>
    </div>

    <script src="https://code.jquery.com/jquery-3.5.1.slim.min.js"></script>
    <script src="https://cdn.jsdelivr.net/npm/@popperjs/core@2.9.3/dist/umd/popper.min.js"></script>
    <script src="https://stackpath.bootstrapcdn.com/bootstrap/4.5.2/js/bootstrap.min.js"></script>
</body>
</html>

<?php
// Close connection
$stmt->close();
$conn->close();
?>
