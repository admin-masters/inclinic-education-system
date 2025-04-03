<?php
ini_set('display_errors', 1);
ini_set('display_startup_errors', 1);
include '../../config/constants.php'; 

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

// Fetch the data for CSV download
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
";

$stmt = $conn->prepare($sql);
$stmt->bind_param("s", $brand_campaign_id);
$stmt->execute();
$result = $stmt->get_result();

// Output headers so that the file is downloaded rather than displayed
header('Content-Type: text/csv; charset=utf-8');
header('Content-Disposition: attachment; filename=field_id_data.csv');

// Create a file pointer connected to the output stream
$output = fopen('php://output', 'w');

// Output column headings
fputcsv($output, array('Zone', 'Region', 'Area', 'Field ID', 'DR ID', 'Doctor Name', 'Phone', 'Collateral ID 272', 'Viewed Collateral ID 272', 'Collateral ID 276', 'Viewed Collateral ID 276', 'Collateral ID 273', 'Viewed Collateral ID 273', 'Collateral ID 277', 'Viewed Collateral ID 277'));

// Fetch data from the result set
while ($row = $result->fetch_assoc()) {
    // Find corresponding CSV data based on Field ID and Phone
    $csv_row = array_filter($csv_data, function($csv_item) use ($row) {
        return $csv_item['Field ID'] === $row['field_id'] && $csv_item['Phone'] === $row['phone'];
    });

    // Get the first match from the filtered result
    $csv_row = reset($csv_row);

    // Check for collateral presence in collateral_transactions table
    $mobile_number = $row['phone'];

    // Query to check for collateral_id 272 and viewed status
    $sql_viewed_272 = "SELECT COUNT(*) AS count, MAX(viewed) AS viewed FROM collateral_transactions WHERE doctor_number = ? AND collateral_id = 272";
    $stmt_viewed_272 = $conn->prepare($sql_viewed_272);
    $stmt_viewed_272->bind_param("s", $mobile_number);
    $stmt_viewed_272->execute();
    $result_viewed_272 = $stmt_viewed_272->get_result();
    $row_viewed_272 = $result_viewed_272->fetch_assoc();
    $collateral_272 = ($row_viewed_272['count'] > 0) ? '1' : '0';
    $viewed_272 = $row_viewed_272['viewed'] ?? '0';

    // Query to check for collateral_id 276 and viewed status
    $sql_viewed_276 = "SELECT COUNT(*) AS count, MAX(viewed) AS viewed FROM collateral_transactions WHERE doctor_number = ? AND collateral_id = 276";
    $stmt_viewed_276 = $conn->prepare($sql_viewed_276);
    $stmt_viewed_276->bind_param("s", $mobile_number);
    $stmt_viewed_276->execute();
    $result_viewed_276 = $stmt_viewed_276->get_result();
    $row_viewed_276 = $result_viewed_276->fetch_assoc();
    $collateral_276 = ($row_viewed_276['count'] > 0) ? '1' : '0';
    $viewed_276 = $row_viewed_276['viewed'] ?? '0';

    $sql_viewed_273 = "SELECT COUNT(*) AS count, MAX(viewed) AS viewed FROM collateral_transactions WHERE doctor_number = ? AND collateral_id = 273";
    $stmt_viewed_273 = $conn->prepare($sql_viewed_273);
    $stmt_viewed_273->bind_param("s", $mobile_number);
    $stmt_viewed_273->execute();
    $result_viewed_273 = $stmt_viewed_273->get_result();
    $row_viewed_273 = $result_viewed_273->fetch_assoc();
    $collateral_273 = ($row_viewed_273['count'] > 0) ? '1' : '0';
    $viewed_273 = $row_viewed_273['viewed'] ?? '0';

    $sql_viewed_277 = "SELECT COUNT(*) AS count, MAX(viewed) AS viewed FROM collateral_transactions WHERE doctor_number = ? AND collateral_id = 277";
    $stmt_viewed_277 = $conn->prepare($sql_viewed_277);
    $stmt_viewed_277->bind_param("s", $mobile_number);
    $stmt_viewed_277->execute();
    $result_viewed_277 = $stmt_viewed_277->get_result();
    $row_viewed_277 = $result_viewed_277->fetch_assoc();
    $collateral_277 = ($row_viewed_277['count'] > 0) ? '1' : '0';
    $viewed_277 = $row_viewed_277['viewed'] ?? '0';

    // Output each row of the data
    fputcsv($output, array(
        $csv_row['Zone'] ?? '',
        $csv_row['Region'] ?? '',
        $csv_row['Area'] ?? '',
        $row['field_id'],
        $csv_row['DR ID'] ?? '',
        $row['doctor_name'],
        $row['phone'],
        $collateral_272,
        $viewed_272,
        $collateral_276,
        $viewed_276,
        $collateral_273,
        $viewed_273,
        $collateral_277,
        $viewed_277
    ));
}

// Close connection
$stmt->close();
$conn->close();
?>
