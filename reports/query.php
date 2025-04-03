<?php
// Display all errors
error_reporting(E_ALL);
ini_set('display_errors', 1);

include 'config/constants.php';

// SQL query to fetch all data from field_reps
$sql = "SELECT * FROM doctors WHERE brand_campaign_id = 'MHlvVeLT'";
$result = $conn->query($sql);

// Check if data exists
if ($result && $result->num_rows > 0) {
    // Set headers to download the file as CSV
    header('Content-Type: text/csv');
    header('Content-Disposition: attachment; filename="field_reps.csv"');

    // Open output stream
    $output = fopen('php://output', 'w');

    // Fetch and output column headings
    $columns = array_keys($result->fetch_assoc());
    fputcsv($output, $columns);

    // Reset result pointer and output each row of the data
    $result->data_seek(0); // Move back to the first row
    while ($row = $result->fetch_assoc()) {
        fputcsv($output, $row);
    }

    // Close the output stream
    fclose($output);
    exit;
} else {
    echo "No data found.";
}

// Close the connection
$conn->close();
?>

<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>CSV Download</title>
</head>
<body>
    <form method="POST">
        <button type="submit">Download CSV</button>
    </form>
</body>
</html>
