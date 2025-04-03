<?php
ini_set('display_errors', 1);
ini_set('display_startup_errors', 1);
// Include the cic.php file to use database connection details
include '../../config/constants.php'; 

// Remove any execution time limits and set memory limit to handle large data
set_time_limit(0);
ini_set('memory_limit', '-1');

// Initialize an empty array for regions
$regions = [];

// Debugging: Check if the file exists
if (!file_exists("Region.csv")) {
    die("Error: Region.csv file not found.");
}

// Open the CSV file for reading
if (($handle = fopen("Region.csv", "r")) !== FALSE) {
    // Loop through the file and read each line as an associative array
    while (($data = fgetcsv($handle, 1000, ",")) !== FALSE) {
        // Ensure there are at least two columns in the CSV
        if (count($data) < 2) continue;

        // Assuming the CSV has two columns: 'Region' and 'Field ID'
        $field_id = trim($data[1]); // Column 2 (Field ID)
        $region_name = trim($data[0]); // Column 1 (Region)
        $regions[$field_id] = $region_name; // Map Field ID to Region
    }
    fclose($handle); // Close the file after reading
} else {
    die("Error: Unable to open Region.csv file.");
}

// Sanitize and fetch the brand_campaign_id, start date, and end date from the GET request
$brand_campaign_id = isset($_GET['brand_campaign_id']) ? mysqli_real_escape_string($conn, $_GET['brand_campaign_id']) : '';
$start_date = isset($_GET['start_date']) ? mysqli_real_escape_string($conn, $_GET['start_date']) : '';
$end_date = isset($_GET['end_date']) ? mysqli_real_escape_string($conn, $_GET['end_date']) : '';

// Check if the Brand_Campaign_ID is not empty
if (empty($brand_campaign_id)) {
    die("Error: Brand Campaign ID is required.");
}

// Get today's date
$today = date('Y-m-d');

// Apply CSS for styling
echo "<style>
body {
    font-family: Arial, sans-serif;
    margin: 20px;
}
h2 {
    color: #333;
    margin-bottom: 20px;
}
form {
    margin-bottom: 20px;
}
label {
    font-weight: bold;
    margin-right: 10px;
}
input[type='date'] {
    padding: 5px;
    border: 1px solid #ccc;
    border-radius: 4px;
    margin-right: 10px;
    max-width: 150px;
}
button {
    padding: 5px 10px;
    background-color: #333;
    color: white;
    border: none;
    border-radius: 4px;
    cursor: pointer;
}
button:hover {
    background-color: #555;
}
.clear-button {
    padding: 5px 10px;
    background-color: #333;
    color: white;
    border: none;
    border-radius: 4px;
    cursor: pointer;
    margin-left: 10px;
}
.clear-button:hover {
    background-color: #555;
}
.home-button, .download-pdf-button {
    padding: 5px 10px;
    background-color: #333;
    color: white;
    border: none;
    border-radius: 4px;
    text-decoration: none;
    display: inline-block;
    margin-right: 10px;
}
.home-button:hover, .download-pdf-button:hover {
    background-color: #555;
}

table {
    width: 100%;
    border-collapse: collapse;
    margin-top: 20px;
}
th, td {
    border: 1px solid #ddd;
    padding: 8px;
    text-align: left;
}
th {
    background-color: #333;
    color: #fff;
}
tr:nth-child(even) {
    background-color: #f2f2f2;
}
tr:hover {
    background-color: #ddd;
}
.cumulative-button{
    padding: 5px 10px;
    background-color: #333;
    color: white;
    border: none;
    border-radius: 4px;
    text-decoration: none;
    display: inline-block;
    margin-right: 10px;
}
</style>";

// Heading
echo "<center><h2>Brand Data {$brand_campaign_id} </h2></center>";

// Form for date selection
echo '<form method="GET" action="index.php">
<center>
    <label for="start_date">Start Date:</label>
    <input type="date" id="start_date" name="start_date" max="' . $today . '" value="' . htmlspecialchars($start_date) . '">
    <label for="end_date">End Date:</label>
    <input type="date" id="end_date" name="end_date" max="' . $today . '" value="' . htmlspecialchars($end_date) . '">
    <input type="hidden" name="brand_campaign_id" value="' . htmlspecialchars($brand_campaign_id) . '"> 
    <br><br>
    <button type="submit">Filter</button>
    <button type="button" class="clear-button" onclick="window.location.href=\'index.php?brand_campaign_id=' . htmlspecialchars($brand_campaign_id) . '\'">Clear</button>
</center>
</form>';

// Add Download CSV button
echo '<form method="POST" action="download_csv.php">
    <a href="../dashboard.php" class="home-button">Home</a>

    <input type="hidden" name="brand_campaign_id" value="' . htmlspecialchars($brand_campaign_id) . '">
    <input type="hidden" name="start_date" value="' . htmlspecialchars($start_date) . '">
    <input type="hidden" name="end_date" value="' . htmlspecialchars($end_date) . '">
    <center>
        <button type="submit">Download as CSV</button>
        <a target="_blank" href="../PDF/index.php?start_date=' . urlencode($start_date) . '&end_date=' . urlencode($end_date) . '&brand_campaign_id=' . urlencode($brand_campaign_id) . '" class="download-pdf-button">Download as PDF</a>
        <a href="https://' . htmlspecialchars($reports) . '.' . htmlspecialchars($cpd) . '/reports/collateral_report_portal/common_report.php?brand_campaign_id=' . urlencode($brand_campaign_id) . '" class="cumulative-button">Cumulative</a>
    </center>
</form>';





// Date validation checks
if ($start_date && $end_date && $start_date > $end_date) {
    die("Please select a start date preceding the end date.");
}

// Construct the SQL query based on date inputs
$query = "SELECT * FROM collateral_transactions WHERE Brand_Campaign_ID = '$brand_campaign_id'";

// If both dates are set, filter between them
if ($start_date && $end_date) {
    $query .= " AND transaction_date BETWEEN '$start_date' AND '$end_date'";
// If only start date is set, filter from start date to today
} elseif ($start_date) {
    $query .= " AND transaction_date >= '$start_date' AND transaction_date <= '$today'";
// If only end date is set, filter from the beginning to the end date
} elseif ($end_date) {
    $query .= " AND transaction_date <= '$end_date'";
}

$result = mysqli_query($conn, $query);

// Check if the query was successful
if (!$result) {
    die("Query failed: " . mysqli_error($conn));
}

// Debugging: Check if any rows are returned
if (mysqli_num_rows($result) == 0) {
    die("No data found for the specified Brand Campaign ID.");
}

// Initialize dictionaries for counts
$used_phone_numbers = [];
$total_id = [];
$seven_days = [];

// Calculate the date for 7 days ago from the selected end date or today if end date is not set
$seven_days_ago = $end_date ? date('Y-m-d H:i:s', strtotime($end_date . ' -7 days')) : date('Y-m-d H:i:s', strtotime($today . ' -7 days'));

// Process data from the database
while ($row = mysqli_fetch_assoc($result)) {
    $phone = $row['doctor_number'];
    $field_id = trim($row['field_id']); // Trim spaces to avoid mismatch
    $transaction_date = $row['transaction_date'];

    // Check if phone number is not already used
    if (!in_array($phone, $used_phone_numbers)) {
        $used_phone_numbers[] = $phone; // Add phone number to used list

        // Check if transaction date is within the last 7 days
        if ($transaction_date >= $seven_days_ago) {
            if (isset($seven_days[$field_id])) {
                $seven_days[$field_id] += 1;
            } else {
                $seven_days[$field_id] = 1;
            }
        }

        // Update cumulative count
        if (isset($total_id[$field_id])) {
            $total_id[$field_id] += 1;
        } else {
            $total_id[$field_id] = 1;
        }
    }
}

// Display the data in a table format
echo "<table>";
echo "<thead><tr><th>Field ID</th><th>Last 7 Days (Unique Doctor's Registered Count)</th><th>Cumulative (Unique Doctor's Registered Count)</th><th>Region</th></tr></thead>";
echo "<tbody>";

// Display all rows fetched from the database
foreach ($total_id as $field_id => $cumulative_count) {
    $last_7_days_count = isset($seven_days[$field_id]) ? $seven_days[$field_id] : 0;
    $region = isset($regions[$field_id]) ? $regions[$field_id] : '-'; // Set to '-' if unknown

    echo "<tr>";
    echo "<td>" . htmlspecialchars($field_id) . "</td>";
    echo "<td>" . htmlspecialchars($last_7_days_count) . "</td>";
    echo "<td>" . htmlspecialchars($cumulative_count) . "</td>";
    echo "<td>" . htmlspecialchars($region) . "</td>";
    echo "</tr>";
}

echo "</tbody>";
echo "</table>";

// Close the database connection
mysqli_close($conn);
?>
