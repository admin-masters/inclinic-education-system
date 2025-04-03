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


$query = "
    SELECT field_id, COUNT(DISTINCT mobile_number) AS doctor_count
    FROM doctors
    WHERE Brand_Campaign_ID = ?
    GROUP BY field_id
";
$stmt = $conn->prepare($query);
$stmt->bind_param("s", $brand_campaign_id);
$stmt->execute();
$result = $stmt->get_result();

$doctorCounts = [];
while ($row = $result->fetch_assoc()) {
    $doctorCounts[$row['field_id']] = $row['doctor_count'];
}

$collateralQuery = "
    SELECT field_id, COUNT(DISTINCT doctor_number, collateral_id) AS unique_doctor_count
    FROM collateral_transactions
    WHERE Brand_Campaign_ID = ?
    GROUP BY field_id
";
$stmt = $conn->prepare($collateralQuery);
$stmt->bind_param("s", $brand_campaign_id);
$stmt->execute();
$collateralResult = $stmt->get_result();

$collateralCounts = [];
while ($row = $collateralResult->fetch_assoc()) {
    $collateralCounts[$row['field_id']] = $row['unique_doctor_count'];
}
$collateralViewedQuery = "
    SELECT field_id, COUNT(DISTINCT doctor_number, collateral_id) AS unique_viewed_doctor_count
    FROM collateral_transactions
    WHERE Brand_Campaign_ID = ?
    AND comment = 'collateral viewed'
    GROUP BY field_id
";
$stmt = $conn->prepare($collateralViewedQuery);
$stmt->bind_param("s", $brand_campaign_id);
$stmt->execute();
$collateralViewedResult = $stmt->get_result();

$collateralViewedCounts = [];
while ($row = $collateralViewedResult->fetch_assoc()) {
    $collateralViewedCounts[$row['field_id']] = $row['unique_viewed_doctor_count'];
}

$stmt->close();
$conn->close();
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
        font-family: Arial, sans-serif;
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
        width: 100%; /* Full width for better appearance */
        background-color: white;
        border-radius: 8px;
        overflow: hidden;
        box-shadow: 0 4px 8px rgba(0, 0, 0, 0.1); /* Subtle shadow for depth */
        border-collapse: separate; /* Prevent cell borders from merging */
        border-spacing: 0; /* Remove spacing between cells */
    }
    th {
        background-color: #007bff;
        color: white;
        text-align: center;
        font-size: 16px; /* Make header text a bit larger */
        padding: 12px 15px;
        border-bottom: 2px solid #ddd; /* Add bottom border for better separation */
    }
    td {
        padding: 12px 15px;
        text-align: center;
        font-size: 14px; /* Standard size for body text */
        border-bottom: 1px solid #ddd; /* Add subtle border between rows */
    }
    tr:nth-child(even) {
        background-color: #f2f2f2; /* Alternate row color */
    }
    tr:hover {
        background-color: #e9ecef; /* Slight hover effect */
    }
    h2 {
        font-weight: bold;
        color: #333;
        font-size: 24px; /* Larger title size */
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
    <div class="container mt-5">
        <div class="btn-container">
            <a href="https://<?php echo $reports; ?>.<?php echo $cpd; ?>/reports/Zuventus/dashboard.php" class="btn btn-primary">Dashboard</a>
            <a href="download_csv1.php?start_date=<?php echo urlencode($start_date); ?>&end_date=<?php echo urlencode($end_date); ?>&brand_campaign_id=<?php echo urlencode($brand_campaign_id); ?>" class="btn btn-success">Download CSV</a>
        </div>

        <h2 class="mb-4">Field ID Data</h2>

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
                        <th>Number of Drs</th>
                        <th>Collateral Shared with Dr.</th>
                        <th>Collateral Viewed by Drs.</th>
                    </tr>
                </thead>
                <tbody>
                    <?php
                    // Load the CSV data
if (($handle = fopen($csvFilePath, "r")) !== FALSE) {
    $header = fgetcsv($handle); // Skip the header row
    $currentRow = 0; // Track the current row number

    $empcodeCounts = []; // Array to hold counts by Empcode
    $lastState = null; // To track the last state for total calculation
    $stateTotals = [
        'doctor_count' => 0,
        'collateral_count' => 0,
        'collateral_viewed_count' => 0,
    ];

    $lastState = null; // Initialize lastState to prevent undefined warnings

while (($row = fgetcsv($handle)) !== FALSE) {
    // Skip rows outside of the current page range
    if ($currentRow >= $offset && $currentRow < $offset + $recordsPerPage) {
        $empcode = $row[1];
        $state = $row[0]; // Ensure state is assigned each time, assuming it's in the first column

        // Update the totals for the current Empcode
        if (!isset($empcodeCounts[$empcode])) {
            $empcodeCounts[$empcode] = [
                'doctor_count' => isset($doctorCounts[$empcode]) ? $doctorCounts[$empcode] : 0,
                'collateral_count' => isset($collateralCounts[$empcode]) ? $collateralCounts[$empcode] : 0,
                'collateral_viewed_count' => isset($collateralViewedCounts[$empcode]) ? $collateralViewedCounts[$empcode] : 0,
            ];
        }

        // If the state changes, print the totals for the last state
        if ($lastState !== null && $lastState !== $state) {
            echo "<tr><td colspan='7'><strong>State Total for $lastState:</strong></td>";
            echo "<td>" . $stateTotals['doctor_count'] . "</td>";
            echo "<td>" . $stateTotals['collateral_count'] . "</td>";
            echo "<td>" . $stateTotals['collateral_viewed_count'] . "</td></tr>";

            // Reset state totals for the new state
            $stateTotals = [
                'doctor_count' => 0,
                'collateral_count' => 0,
                'collateral_viewed_count' => 0,
            ];
        }

        // Update the state totals
        $stateTotals['doctor_count'] += $empcodeCounts[$empcode]['doctor_count'];
        $stateTotals['collateral_count'] += $empcodeCounts[$empcode]['collateral_count'];
        $stateTotals['collateral_viewed_count'] += $empcodeCounts[$empcode]['collateral_viewed_count'];

        // Display the current row
        echo "<tr>";
        for ($i = 0; $i < count($row) - 2; $i++) {
            echo "<td>" . htmlspecialchars($row[$i]) . "</td>";
        }
        echo "<td>" . $empcodeCounts[$empcode]['doctor_count'] . "</td>";
        echo "<td>" . $empcodeCounts[$empcode]['collateral_count'] . "</td>";
        echo "<td>" . $empcodeCounts[$empcode]['collateral_viewed_count'] . "</td>";
        echo "</tr>";
    }
    $currentRow++;
    $lastState = $state; // Update the last state
}

// Output totals for the last state
if ($lastState !== null) {
    echo "<tr><td colspan='7'><strong>State Total for $lastState:</strong></td>";
    echo "<td>" . $stateTotals['doctor_count'] . "</td>";
    echo "<td>" . $stateTotals['collateral_count'] . "</td>";
    echo "<td>" . $stateTotals['collateral_viewed_count'] . "</td></tr>";
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
