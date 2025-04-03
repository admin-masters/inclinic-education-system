<?php
// Display errors for debugging
ini_set('display_errors', 1);
ini_set('display_startup_errors', 1);
error_reporting(E_ALL);

include '../../config/constants.php';  // Ensure this file establishes the database connection correctly

// Get the brand campaign ID from the URL or default to an empty string
$brand_campaign_id = isset($_GET['brand_campaign_id']) ? $_GET['brand_campaign_id'] : ''; 

// Get the start date and end date from the URL or default to empty strings
$start_date = isset($_GET['start_date']) ? $_GET['start_date'] : '';
$end_date = isset($_GET['end_date']) ? $_GET['end_date'] : '';

// Set up pagination variables
$limit = 500; // Number of records per page
$page = isset($_GET['page']) ? $_GET['page'] : 1;
$offset = ($page - 1) * $limit;

// Build the date filter conditions
$date_filter = '';
if (!empty($start_date) && !empty($end_date)) {
    $date_filter = " AND transaction_date BETWEEN '$start_date' AND '$end_date'";
}

// Calculate total number of records for pagination
$total_records_query = "SELECT COUNT(*) as total FROM collateral_transactions WHERE Brand_Campaign_ID = '$brand_campaign_id' $date_filter";
$total_records_result = mysqli_query($conn, $total_records_query);
$total_records = mysqli_fetch_assoc($total_records_result)['total'];
$total_pages = ceil($total_records / $limit);

// Load CSV data into an associative array
$csv_file_path = 'csvfile.csv'; // Replace with the actual path to your CSV file
$csv_data = array_map('str_getcsv', file($csv_file_path));
$csv_headers = array_shift($csv_data); // Get headers

$csv_map = [];
foreach ($csv_data as $row) {
    $row_assoc = array_combine($csv_headers, $row);
    $field_id = $row_assoc['Field_id']; // Correct field ID header based on CSV
    $csv_map[$field_id] = $row_assoc; // Map field_id to manager and state
}

// Initialize the collateral IDs
$collateral_ids = [216, 249, 217, 321, 231, 302, 317, 331, 354, 300, 343, 347, 355, 357, 448, 394,410];



// Fetch paginated records from collateral_transactions table for the given brand_campaign_id and date range in ascending order of field_id
$query = "SELECT * FROM collateral_transactions WHERE Brand_Campaign_ID = '$brand_campaign_id' $date_filter ORDER BY field_id ASC LIMIT $limit OFFSET $offset";
$result = mysqli_query($conn, $query);

$data = [];
$doctor_count = []; // To store the count of distinct doctors for each field_id

// Check if the query executed successfully
if ($result) {
    while ($row = mysqli_fetch_assoc($result)) {
        $field_id = $row['field_id'];
        $doctor_number = $row['doctor_number'];
        $collateral_id = $row['collateral_id'];

        // Fetch the doctor name from the doctors table using doctor_number
        $doctor_name = '';
        if (!empty($doctor_number)) {
            $doctor_query = "SELECT name AS doctor_name FROM doctors WHERE mobile_number = '$doctor_number'";
            $doctor_result = mysqli_query($conn, $doctor_query);
            if ($doctor_result && mysqli_num_rows($doctor_result) > 0) {
                $doctor_name = mysqli_fetch_assoc($doctor_result)['doctor_name'] ?? '';
            }
            mysqli_free_result($doctor_result);
        }

        // Fetch the field rep gmail from the field_reps table using field_id
        $field_rep_gmail = '';
        if (!empty($field_id)) {
            $rep_query = "SELECT gmail_id FROM field_reps WHERE field_id = '$field_id'";
            $rep_result = mysqli_query($conn, $rep_query);
            if ($rep_result && mysqli_num_rows($rep_result) > 0) {
                $field_rep_gmail = mysqli_fetch_assoc($rep_result)['gmail_id'] ?? '';
            }
            mysqli_free_result($rep_result);
        }

        // Fetch the manager and state from the CSV data
        $manager = isset($csv_map[$field_id]['Manager Name']) ? $csv_map[$field_id]['Manager Name'] : '';
        $state = isset($csv_map[$field_id]['State']) ? $csv_map[$field_id]['State'] : '';

        // Initialize the key to group records by field_id and doctor_number
        $key = $field_id . '-' . $doctor_number;

        // Format the transaction date (only the date part)
        $transaction_date = date('Y-m-d', strtotime($row['transaction_date']));

        // Count the number of distinct doctors registered by each field_id
        if (!isset($doctor_count[$field_id])) {
            // Fetch distinct doctor numbers for the current field_id
            $distinct_doctor_query = "SELECT COUNT(DISTINCT mobile_number) AS doctor_count FROM doctors WHERE field_id = '$field_id'";
            $distinct_doctor_result = mysqli_query($conn, $distinct_doctor_query);
            $doctor_count[$field_id] = mysqli_fetch_assoc($distinct_doctor_result)['doctor_count'] ?? 0;
            mysqli_free_result($distinct_doctor_result);
        }

        // If this key already exists, append the date; otherwise, create a new entry
        if (isset($data[$key])) {
            if (isset($data[$key]['collateral_dates'][$collateral_id])) {
                // Check if the date is already in the string
                if (strpos($data[$key]['collateral_dates'][$collateral_id], $transaction_date) === false) {
                    // Append the date only if it's not already present
                    if (!empty($data[$key]['collateral_dates'][$collateral_id])) {
                        $data[$key]['collateral_dates'][$collateral_id] .= ', ' . $transaction_date;
                    } else {
                        $data[$key]['collateral_dates'][$collateral_id] = $transaction_date;
                    }
                }
            } else {
                $data[$key]['collateral_dates'][$collateral_id] = $transaction_date;
            }
        } else {
            $collateral_dates = array_fill_keys($collateral_ids, '');

            if (in_array($collateral_id, $collateral_ids)) {
                $collateral_dates[$collateral_id] = $transaction_date;
            }

            $data[$key] = [
                'field_id' => $field_id,
                'field_rep_gmail' => $field_rep_gmail,
                'manager' => $manager,
                'state' => $state,
                'number_of_doctors_registered' => $doctor_count[$field_id], 
                'doctor_name' => $doctor_name,
                'doctor_number' => $doctor_number,
                'collateral_dates' => $collateral_dates
            ];
        }
    }

    mysqli_free_result($result);
} else {
    echo "Error executing query: " . mysqli_error($conn);
}

mysqli_close($conn);
?>


<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Report Table</title>
    <link rel="stylesheet" href="https://stackpath.bootstrapcdn.com/bootstrap/4.5.2/css/bootstrap.min.css">
    <style>
        .table-container {
            margin-top: 1px;
            margin-bottom: 1px;
            overflow-x: auto;
        }
        .pagination {
            justify-content: center;
        }
        .pagination .page-item.disabled .page-link {
            background-color: #f8f9fa;
            color: #6c757d;
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
    <div class="container-fluid">
        <!-- Form to filter by date -->
        <form method="GET" class="form-inline mb-3">
            <input type="hidden" name="brand_campaign_id" value="<?php echo htmlspecialchars($brand_campaign_id); ?>">
            <div class="form-group mx-sm-3 mb-2">
                <label for="start_date" class="mr-2">Start Date:</label>
                <input type="date" name="start_date" id="start_date" value="<?php echo htmlspecialchars($start_date); ?>" class="form-control">
            </div>
            <div class="form-group mx-sm-3 mb-2">
                <label for="end_date" class="mr-2">End Date:</label>
                <input type="date" name="end_date" id="end_date" value="<?php echo htmlspecialchars($end_date); ?>" class="form-control">
            </div>
            <button type="submit" class="btn btn-primary mb-2">Filter</button>
        </form>

        <div class="btn-container">
            <a href="https://<?php echo htmlspecialchars($reports); ?>.<?php echo htmlspecialchars($cpd); ?>/reports/collateral_report_portal/dashboard.php" class="btn btn-primary">Dashboard</a>
            <a href="download_csv.php?brand_campaign_id=<?php echo urlencode($brand_campaign_id); ?>" class="btn btn-success">Download CSV</a>
            <a href="https://<?php echo htmlspecialchars($reports); ?>.<?php echo htmlspecialchars($cpd); ?>/reports/collateral_report_portal/common_report.php?brand_campaign_id=<?php echo urlencode($brand_campaign_id); ?>" class="btn btn-warning">Cumulative</a>
            <a href="https://<?php echo $reports; ?>.<?php echo $cpd; ?>/reports/collateral_report_portal/6ZQtbo4B/collateral_details.php?brand_campaign_id=<?php echo urlencode($brand_campaign_id); ?>" class="btn btn-light">Collateral Details</a>
        </div>
        <h2 class="text-center mb-4">Report Table</h2>
        <div class="table-container">
            <table class="table table-bordered table-striped table-hover">
                <thead class="thead-dark">
                    <tr>
                        <th>Field ID</th>
                        <th>Field Rep Gmail ID</th>
                        <th>Manager</th>
                        <th>State</th>
                        <th>Number of Doctors Registered</th>
                        <th>Doctor Name</th>
                        <th>Doctor Number</th>
                        <th>216</th>
                        <th>249</th>
                        <th>217</th>
                        <th>321</th>
                        <th>231</th>
                        <th>302</th>
                        <th>317</th>
                        <th>331</th>
                        <th>354</th>
                        <th>300</th>
                        <th>343</th>
                        <th>347</th>
                        <th>355</th>
                        <th>357</th>
                        <th>448</th>
                        <th>394</th>
                        <th>410</th>

                    </tr>
                </thead>
                <tbody>
    <?php foreach ($data as $row): ?>
        <tr>
            <td><?php echo htmlspecialchars($row['field_id'] ?? ''); ?></td>
            <td><?php echo htmlspecialchars($row['field_rep_gmail'] ?? ''); ?></td>
            <td><?php echo htmlspecialchars($row['manager'] ?? ''); ?></td>
            <td><?php echo htmlspecialchars($row['state'] ?? ''); ?></td>
            <td><?php echo htmlspecialchars($row['number_of_doctors_registered'] ?? 0); ?></td>
            <td><?php echo htmlspecialchars($row['doctor_name'] ?? ''); ?></td>
            <td><?php echo htmlspecialchars($row['doctor_number'] ?? ''); ?></td>
            <td><?php echo htmlspecialchars($row['collateral_dates'][216] ?? ''); ?></td>
            <td><?php echo htmlspecialchars($row['collateral_dates'][249] ?? ''); ?></td>
            <td><?php echo htmlspecialchars($row['collateral_dates'][217] ?? ''); ?></td>
            <td><?php echo htmlspecialchars($row['collateral_dates'][321] ?? ''); ?></td>
            <td><?php echo htmlspecialchars($row['collateral_dates'][231] ?? ''); ?></td>
            <td><?php echo htmlspecialchars($row['collateral_dates'][302] ?? ''); ?></td>
            <td><?php echo htmlspecialchars($row['collateral_dates'][317] ?? ''); ?></td>
            <td><?php echo htmlspecialchars($row['collateral_dates'][331] ?? ''); ?></td>
            <td><?php echo htmlspecialchars($row['collateral_dates'][354] ?? ''); ?></td>
            <td><?php echo htmlspecialchars($row['collateral_dates'][300] ?? ''); ?></td>   
            <td><?php echo htmlspecialchars($row['collateral_dates'][343] ?? ''); ?></td>
            <td><?php echo htmlspecialchars($row['collateral_dates'][347] ?? ''); ?></td>
            <td><?php echo htmlspecialchars($row['collateral_dates'][355] ?? ''); ?></td>
            <td><?php echo htmlspecialchars($row['collateral_dates'][357] ?? ''); ?></td>
            <td><?php echo htmlspecialchars($row['collateral_dates'][448] ?? ''); ?></td>
            <td><?php echo htmlspecialchars($row['collateral_dates'][394] ?? ''); ?></td>
            <td><?php echo htmlspecialchars($row['collateral_dates'][410] ?? ''); ?></td>
            


        </tr>
    <?php endforeach; ?>
</tbody>
            </table>
        </div>
        <!-- Pagination -->
        <nav aria-label="Page navigation">
            <ul class="pagination">
                <?php for ($i = 1; $i <= $total_pages; $i++): ?>
                    <li class="page-item <?php echo ($i == $page) ? 'active' : ''; ?>">
                        <a class="page-link" href="?brand_campaign_id=<?php echo $brand_campaign_id; ?>&start_date=<?php echo urlencode($start_date); ?>&end_date=<?php echo urlencode($end_date); ?>&page=<?php echo $i; ?>"><?php echo $i; ?></a>
                    </li>
                <?php endfor; ?>
            </ul>
        </nav>
    </div>
</body>
</html>