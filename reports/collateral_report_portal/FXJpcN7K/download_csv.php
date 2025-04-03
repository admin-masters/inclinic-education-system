<?php
ini_set('display_errors', 1);
ini_set('display_startup_errors', 1);
include '../../config/constants.php';


// SQL query to fetch all data from the 'wallace' table with the collateral information
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
        MAX(CASE WHEN ct.collateral_id = 277 AND ct.viewed = 1 THEN 1 ELSE 0 END) AS viewed_277
    FROM wallace w
    LEFT JOIN collateral_transactions ct 
        ON w.field_id = ct.field_id AND w.doctor_number = ct.doctor_number
    GROUP BY w.zone, w.region, w.area, w.field_id, w.doctor_id, w.doctor_name, w.doctor_number
";

$result = $conn->query($sql);

if ($result->num_rows > 0) {
    // Set headers to indicate that this is a CSV file
    header('Content-Type: text/csv; charset=utf-8');
    header('Content-Disposition: attachment; filename=field_id_data.csv');

    // Open the output stream
    $output = fopen('php://output', 'w');

    // Output the column headings
    fputcsv($output, array('Zone', 'Region', 'Area', 'Field ID', 'DR ID', 'Doctor Name', 'Phone', 'Collateral ID 272', 'Viewed Collateral ID 272', 'Collateral ID 276', 'Viewed Collateral ID 276', 'Collateral ID 273', 'Viewed Collateral ID 273', 'Collateral ID 277', 'Viewed Collateral ID 277'));

    // Output the rows of data
    while ($row = $result->fetch_assoc()) {
        fputcsv($output, array(
            $row['zone'],
            $row['region'],
            $row['area'],
            $row['field_id'],
            $row['doctor_id'],
            $row['doctor_name'],
            $row['doctor_number'],
            $row['collateral_272'],
            $row['viewed_272'],
            $row['collateral_276'],
            $row['viewed_276'],
            $row['collateral_273'],
            $row['viewed_273'],
            $row['collateral_277'],
            $row['viewed_277']
        ));
    }

    // Close the output stream
    fclose($output);
} else {
    echo "No records found.";
}

$conn->close();
?>
