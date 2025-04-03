<?php
ini_set('display_errors', 1);
ini_set('display_startup_errors', 1);
include '../../config/constants.php'; 

$brand_campaign_id = isset($_GET['brand_campaign_id']) ? $_GET['brand_campaign_id'] : '';
$start_date = isset($_GET['start_date']) ? $_GET['start_date'] : '';
$end_date = isset($_GET['end_date']) ? $_GET['end_date'] : '';

// File path to the CSV file
$csvFilePath = 'Report.csv'; // Change this to the actual path of the CSV file

// Number of records per page
$recordsPerPage = 500;
$page = isset($_GET['page']) ? intval($_GET['page']) : 1;
$offset = ($page - 1) * $recordsPerPage;

// Function to fetch collateral transaction dates
function fetchCollateralSharedDates($field_id, $doctor_number, $conn) {
    $dates = 'N/A'; // Default to 'N/A' if no dates are found
    $query = "SELECT GROUP_CONCAT(transaction_date SEPARATOR ', ') AS dates 
              FROM collateral_transactions 
              WHERE field_id = ? 
              AND doctor_number = ? 
              AND comment = 'Collateral Shared'";
    $stmt = $conn->prepare($query);
    
    // Bind parameters and execute the query
    $stmt->bind_param('ss', $field_id, $doctor_number);
    $stmt->execute();
    
    // Initialize the result variable
    $stmt->bind_result($dateList);
    
    // Fetch the result
    if ($stmt->fetch()) {
        $dates = $dateList ? $dateList : 'N/A'; // If result is empty, default to 'N/A'
    }
    
    $stmt->close();
    return $dates;
}

function fetchCollateralViewedDates($field_id, $doctor_number, $conn) {
    $dates = 'N/A'; // Default to 'N/A' if no dates are found
    $query = "SELECT GROUP_CONCAT(transaction_date SEPARATOR ', ') AS dates 
              FROM collateral_transactions 
              WHERE field_id = ? 
              AND doctor_number = ? 
              AND comment = 'collateral viewed'";
    $stmt = $conn->prepare($query);
    
    // Bind parameters and execute the query
    $stmt->bind_param('ss', $field_id, $doctor_number);
    $stmt->execute();
    
    // Initialize the result variable
    $stmt->bind_result($dateList);
    
    // Fetch the result
    if ($stmt->fetch()) {
        $dates = $dateList ? $dateList : 'N/A'; // If result is empty, default to 'N/A'
    }
    
    $stmt->close();
    return $dates;
}
function fetchVideoViewedDates($field_id, $doctor_number, $conn) {
    $dates = 'N/A'; // Default to 'N/A' if no dates are found
    $query = "SELECT GROUP_CONCAT(transaction_date SEPARATOR ', ') AS dates 
              FROM collateral_transactions 
              WHERE field_id = ? 
              AND doctor_number = ? 
              AND comment = 'Video Viewed'";
    $stmt = $conn->prepare($query);
    
    // Bind parameters and execute the query
    $stmt->bind_param('ss', $field_id, $doctor_number);
    $stmt->execute();
    
    // Initialize the result variable
    $stmt->bind_result($dateList);
    
    // Fetch the result
    if ($stmt->fetch()) {
        $dates = $dateList ? $dateList : 'N/A'; // If result is empty, default to 'N/A'
    }
    
    $stmt->close();
    return $dates;
}

function fetchCollateralViewedDuration($field_id, $doctor_number, $conn) {
    $viewed_duration = 'N/A'; // Default to 'N/A' if no viewed duration is found
    $viewedValue = null;
    
    $query = "SELECT MAX(video_pec) AS viewed_duration 
              FROM collateral_transactions 
              WHERE field_id = ? 
              AND doctor_number = ? 
              AND comment = 'Video Viewed'";
    
    $stmt = $conn->prepare($query);
    $stmt->bind_param('ss', $field_id, $doctor_number);
    $stmt->execute();
    $stmt->bind_result($viewedValue);
    
    if ($stmt->fetch()) {
        if ($viewedValue == 1) {
            $viewed_duration = ">50%";
        } elseif ($viewedValue == 2) {
            $viewed_duration = "<50%";
        } elseif ($viewedValue == 3) {
            $viewed_duration = "100%";
        } else {
            $viewed_duration = 'N/A';
        }
    }
    
    $stmt->close();
    return $viewed_duration;
}

// Get total number of rows in CSV
$totalRows = 0;
if (($handle = fopen($csvFilePath, "r")) !== FALSE) {
    while (($row = fgetcsv($handle)) !== FALSE) {
        $totalRows++;
    }
    fclose($handle);
}

// Calculate total pages
$totalPages = ceil(($totalRows - 1) / $recordsPerPage); // Minus header row
?>

<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Field ID Data</title>
    <link href="https://stackpath.bootstrapcdn.com/bootstrap/4.5.2/css/bootstrap.min.css" rel="stylesheet">
    <style>
        body {
            background-color: #f8f9fa;
        }
        .btn-container {
            display: flex;
            justify-content: start;
            gap: 10px;
            margin-bottom: 20px;
        }
        .table-container {
            margin-top: 20px;
        }
        table {
            background-color: white;
            border-radius: 8px;
            overflow: hidden;
            box-shadow: 0 2px 4px rgba(0, 0, 0, 0.1);
        }
        th {
            background-color: #007bff;
            color: white;
        }
        th, td {
            padding: 12px 15px;
            text-align: left;
        }
        tr:nth-child(even) {
            background-color: #f2f2f2;
        }
        h2 {
            font-weight: bold;
            color: #333;
        }
        .table-responsive {
            border-radius: 8px;
        }
        .pagination {
            justify-content: center; /* Centers the pagination controls */
            margin-top: 20px;
        }
        .pagination .page-link {
            color: #007bff; /* Blue text for pagination links */
        }
        .pagination .page-item.active .page-link {
            background-color: #007bff; /* Active page link color */
            border-color: #007bff;
            color: white;
        }
        .pagination .page-link:hover {
            background-color: #0056b3; /* Darker blue on hover */
            color: white;
        }
        .pagination .page-link {
            border: 1px solid #dee2e6; /* Light border for page links */
            border-radius: 50%; /* Rounded pagination buttons */
            padding: 10px 15px; /* Spacing for buttons */
        }
        .pagination .page-link:focus {
            outline: none; /* Remove the focus outline */
            box-shadow: 0 0 0 0.2rem rgba(0, 123, 255, 0.25); /* Subtle blue shadow on focus */
        }
    </style>
</head>
<body>
    <div class="container mt-5">
        <div class="btn-container">
            <a href="https://<?php echo $reports; ?>.<?php echo $cpd; ?>/reports/collateral_report_portal/dashboard.php" class="btn btn-primary">Dashboard</a>
            <a href="download_csv.php?start_date=<?php echo urlencode($start_date); ?>&end_date=<?php echo urlencode($end_date); ?>&brand_campaign_id=<?php echo urlencode($brand_campaign_id); ?>" class="btn btn-success">Download CSV</a>
            <a href="https://<?php echo $reports; ?>.<?php echo $cpd; ?>/reports/collateral_report_portal/common_report.php?brand_campaign_id=<?php echo urlencode($brand_campaign_id); ?>" class="btn btn-warning">Cumulative</a>
            <a href="index1.php?brand_campaign_id=<?php echo urlencode($brand_campaign_id); ?>" class="btn btn-danger">Report 2</a>
            <a href="https://<?php echo $reports; ?>.<?php echo $cpd; ?>/reports/collateral_report_portal/KLx5Yatf/collateral_details.php?brand_campaign_id=<?php echo urlencode($brand_campaign_id); ?>" class="btn btn-light">Collateral Details</a>
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

        <!-- Table to display CSV data -->
        <div class="table-container table-responsive">
            <table class="table table-striped table-bordered">
                <thead>
                    <tr>
                        <th>State</th>
                        <th>Empcode</th>
                        <th>Position Code</th>
                        <th>Empname</th>
                        <th>HQ</th>
                        <th>Emp Mob No.</th>
                        <th>MCL No</th>
                        <th>Doctors Name</th>
                        <th>Mobile</th>
                        <th>Collateral Shared with Dr.</th>
                        <th>Collateral Viewed by Dr.</th>
                        <th>Collateral Viewed by Dr. Duration of Time</th>
                        <th>Date when Viewed</th>
                    </tr>
                </thead>
                <tbody>
                    <?php
                    // Connect to the database and load the CSV data
                    if (($handle = fopen($csvFilePath, "r")) !== FALSE) {
                        $header = fgetcsv($handle); // Skip the header row
                        $currentRow = 0; // Track the current row number

                        while (($row = fgetcsv($handle)) !== FALSE) {
                            // Skip rows outside of the current page range
                            if ($currentRow >= $offset && $currentRow < $offset + $recordsPerPage) {
                                echo "<tr>";
                                for ($i = 0; $i < count($row); $i++) {
                                    echo "<td>" . htmlspecialchars($row[$i]) . "</td>";
                                }

                                // Fetch additional details from database using field_id and doctor_number
                                $field_id = $row[1]; // Assuming Empcode is the second column
                                $doctor_number = $row[8]; // Assuming Mobile is the 10th column

                                $collateral_shared_dates = fetchCollateralSharedDates($field_id, $doctor_number, $conn);
                                echo "<td>" . htmlspecialchars($collateral_shared_dates) . "</td>";

                                $collateral_viewed_dates = fetchCollateralViewedDates($field_id, $doctor_number, $conn);
                                echo "<td>" . htmlspecialchars($collateral_viewed_dates) . "</td>";

                                $collateral_viewed_duration = fetchCollateralViewedDuration($field_id, $doctor_number, $conn);
                                echo "<td>" . htmlspecialchars($collateral_viewed_duration) . "</td>";

                                $video_viewed_dates = fetchVideoViewedDates($field_id, $doctor_number, $conn);
                                echo "<td>" . htmlspecialchars($video_viewed_dates) . "</td>";

                                echo "</tr>";
                            }
                            $currentRow++;
                        }
                        fclose($handle);
                    }
                    ?>
                </tbody>
            </table>
        </div>

        <!-- Pagination -->
        <nav aria-label="Page navigation">
            <ul class="pagination justify-content-center">
                <?php if ($page > 1): ?>
                    <li class="page-item"><a class="page-link" href="?page=<?php echo $page - 1; ?>&brand_campaign_id=<?php echo urlencode($brand_campaign_id); ?>&start_date=<?php echo urlencode($start_date); ?>&end_date=<?php echo urlencode($end_date); ?>">Previous</a></li>
                <?php endif; ?>

                <?php for ($i = 1; $i <= $totalPages; $i++): ?>
                    <li class="page-item <?php echo $i == $page ? 'active' : ''; ?>">
                        <a class="page-link" href="?page=<?php echo $i; ?>&brand_campaign_id=<?php echo urlencode($brand_campaign_id); ?>&start_date=<?php echo urlencode($start_date); ?>&end_date=<?php echo urlencode($end_date); ?>">
                            <?php echo $i; ?>
                        </a>
                    </li>
                <?php endfor; ?>

                <?php if ($page < $totalPages): ?>
                    <li class="page-item"><a class="page-link" href="?page=<?php echo $page + 1; ?>&brand_campaign_id=<?php echo urlencode($brand_campaign_id); ?>&start_date=<?php echo urlencode($start_date); ?>&end_date=<?php echo urlencode($end_date); ?>">Next</a></li>
                <?php endif; ?>
            </ul>
        </nav>
    </div>
</body>
</html>
