<?php
ini_set('display_errors', 1);
ini_set('display_startup_errors', 1);
include '../../config/constants.php';

header('Content-Type: text/csv; charset=utf-8');
header('Content-Disposition: attachment; filename=filtered_data.csv');

// Create a file pointer connected to the output stream
$output = fopen('php://output', 'w');

// Output the column headings
fputcsv($output, array(
    'Zone',
    'Region',
    'Area',
    'Field ID',
    'DR ID',
    'Doctor Name',
    'Phone',
    'Mini CME 1 Managing High-Volume Pediatric Diarrhoea Collateral share',
    'No of Drs have Viewed Collaterals (Mini CME 1 Managing High-Volume Pediatric Diarrhoea)',
    'Case Study on conditions linked to diarrhoea and nutrition - Issue 1 Collateral Share',
    'No of Drs have Viewed Collaterals (Case study 1 on conditions linked to diarrhoea and nutrition - Issue 1)',
    'Mini CME Issue 2 on Understanding Diarrhoea and the Role of Antibiotics in Children Collateral share',
    'No of Drs have Viewed CollateralsMini CME Issue 2 on Understanding Diarrhoea and the Role of Antibiotics in Children',
    'Case Study Issue 2 on conditions related to diarrhoea & nutrition collateral shared',
    'No of Doctors have viewed Case Study Issue 2 on conditions related to diarrhoea & nutrition',
    'Mini CME Issue 3 Blood and Mucus in Pediatric Stools: Causes and Concerns collateral shared',
    'No of Doctors have viewed Mini CME Issue 3 Blood and Mucus in Pediatric Stools: Causes and Concerns',
    'Case Study Issue 3 on conditions related to diarrhoea & nutrition collateral shared',
    'No of Doctors have viewed Case Study Issue 3 on conditions related to diarrhoea & nutrition',
    'Mini CME Issue 4 on Fever in Pediatric Diarrhea: Infectious vs. Inflammatory Causes collateral shared',
    'No of Doctors have viewed Mini CME Issue 4 on Fever in Pediatric Diarrhea: Infectious vs. Inflammatory Causes',
    'Case Study Issue 4 on conditions linked to Integrative Management of Pediatric Diarrhoea: Post-Infectious IBS and Probiotic-Supported Dietary Interventions collateral shared',
    'No of Doctors have viewed Case Study Issue 4 on conditions linked to Integrative Management of Pediatric Diarrhoea: Post-Infectious IBS and Probiotic-Supported Dietary Interventions'
));

// Single search term for all columns (if provided)
$search_term = isset($_GET['search']) ? $_GET['search'] : '';

// SQL query to fetch either filtered data or full data
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
        MAX(CASE WHEN ct.collateral_id = 274 THEN 1 ELSE 0 END) AS collateral_274,
        MAX(CASE WHEN ct.collateral_id = 274 AND ct.viewed = 1 THEN 1 ELSE 0 END) AS viewed_274,
        MAX(CASE WHEN ct.collateral_id = 421 THEN 1 ELSE 0 END) AS collateral_421,
        MAX(CASE WHEN ct.collateral_id = 421 AND ct.viewed = 1 THEN 1 ELSE 0 END) AS viewed_421,
        MAX(CASE WHEN ct.collateral_id = 275 THEN 1 ELSE 0 END) AS collateral_275,
        MAX(CASE WHEN ct.collateral_id = 275 AND ct.viewed = 1 THEN 1 ELSE 0 END) AS viewed_275,
        MAX(CASE WHEN ct.collateral_id = 397 THEN 1 ELSE 0 END) AS collateral_397,
        MAX(CASE WHEN ct.collateral_id = 397 AND ct.viewed = 1 THEN 1 ELSE 0 END) AS viewed_397
    FROM wallace w
    LEFT JOIN collateral_transactions ct 
        ON w.field_id = ct.field_id AND w.doctor_number = ct.doctor_number";

// Append WHERE clause if a search term is provided
if (!empty($search_term)) {
    $sql .= "
        WHERE (w.zone LIKE '%$search_term%' 
            OR w.region LIKE '%$search_term%' 
            OR w.area LIKE '%$search_term%' 
            OR w.field_id LIKE '%$search_term%' 
            OR w.doctor_id LIKE '%$search_term%' 
            OR w.doctor_name LIKE '%$search_term%' 
            OR w.doctor_number LIKE '%$search_term%')
    ";
}

$sql .= " GROUP BY w.zone, w.region, w.area, w.field_id, w.doctor_id, w.doctor_name, w.doctor_number";

// Execute the query
$result = $conn->query($sql);

// Check if any rows were returned
if ($result->num_rows > 0) {
    // Loop through the rows and write each to the CSV file
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
            $row['viewed_277'],
            $row['collateral_274'],
            $row['viewed_274'],
            $row['collateral_421'],
            $row['viewed_421'],
            $row['collateral_275'],
            $row['viewed_275'],
            $row['collateral_397'],
            $row['viewed_397']
        ));
    }
} else {
    // No data found, output an empty row (this is optional)
    fputcsv($output, array('No data found for the given search term'));
}

// Close the output stream
fclose($output);
exit();
