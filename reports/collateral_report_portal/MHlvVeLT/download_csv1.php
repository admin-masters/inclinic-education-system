<?php
ini_set('display_errors', 1);
ini_set('display_startup_errors', 1);
error_reporting(E_ALL);
include '../../config/constants.php'; 

$brand_campaign_id = isset($_GET['brand_campaign_id']) ? $_GET['brand_campaign_id'] : '';

header('Content-Type: text/csv; charset=utf-8');
header('Content-Disposition: attachment; filename="report.csv"');

// Open the output stream
$output = fopen('php://output', 'w');

// Define the header row based on multiple collateral_ids
fputcsv($output, [
    'NAME OF STAFF',
    'EMPLOYEE CODE',
    'HQ',
    'STAFF WHATSAPP NUMBER',
    'PEDIATRICIAN\'S NAME',
    'PEDIATRICIAN\'S WHATSAPP NUMBER',
    'STATE',
    'Date on which "Case Study - The Science of Baby Skin" Collateral was shared',
    'Date on which the doctor clicked on the link',
    'Date on which "Mini CME on Diaper Dermatitis: From Prevention to Treatment" Collateral was shared',
    'Date on which the doctor clicked on the link',
    'Date on which "Mini CME on Diaper Dermatitis (Alternate)" Collateral was shared',
    'Date on which the doctor clicked on the link'
]);

// Path to the CSV file being used in the main script
$csv_file = 'report.csv';

if (file_exists($csv_file) && is_readable($csv_file)) {
    if (($handle = fopen($csv_file, 'r')) !== false) {
        $header = fgetcsv($handle); // Skip the header row

        // Define collateral IDs for which we need data.
        // Here, 407 and 337 are mini CMEs and 387 is the case study.
        $collateral_ids = [
            407 => 'Mini CME on The Science of Baby Skin : Understanding the Dermatological Needs of Infants',
            337 => 'Mini CME on Diaper Dermatitis: From Prevention to Treatment',
            387 => 'Case Study - The Science of Baby Skin: Understanding the Dermatological Needs of Infants'
        ];

        while (($data = fgetcsv($handle)) !== false) {
            $employee_code = $data[1]; // EMPLOYEE CODE
            $doctor_number = $data[5]; // PEDIATRICIAN'S WHATSAPP NUMBER

            // Fetch transaction dates in one query for the given collateral_ids
            $placeholders = implode(',', array_fill(0, count($collateral_ids), '?'));
            $query = "
                SELECT collateral_id, transaction_date, viewed 
                FROM MHlvVeLT 
                WHERE field_id = ? AND doctor_number = ? AND collateral_id IN ($placeholders)
            ";

            $stmt = $conn->prepare($query);
            $params = array_merge([$employee_code, $doctor_number], array_keys($collateral_ids));
            $stmt->bind_param(str_repeat('s', count($params)), ...$params);
            $stmt->execute();
            $result = $stmt->get_result();

            // Store retrieved dates by collateral_id
            $transaction_dates = [];
            while ($row = $result->fetch_assoc()) {
                $key = $row['collateral_id'];
                $transaction_dates[$key]['shared'] = $row['transaction_date'];
                if ($row['viewed'] == 1) {
                    $transaction_dates[$key]['viewed'] = $row['transaction_date'];
                }
            }
            $stmt->close();

            // Prepare data for CSV output
            fputcsv($output, [
                $data[0], // NAME OF STAFF
                $data[1], // EMPLOYEE CODE
                $data[2], // HQ
                $data[3], // STAFF WHATSAPP NUMBER
                $data[4], // PEDIATRICIAN'S NAME
                $data[5], // PEDIATRICIAN'S WHATSAPP NUMBER
                $data[6], // STATE
                $transaction_dates[387]['shared'] ?? 'Not Found', // Case Study Shared
                $transaction_dates[387]['viewed'] ?? 'Not Found', // Case Study Viewed
                $transaction_dates[407]['shared'] ?? 'Not Found', // Mini CME (407) Shared
                $transaction_dates[407]['viewed'] ?? 'Not Found', // Mini CME (407) Viewed
                $transaction_dates[337]['shared'] ?? 'Not Found', // Mini CME (337) Shared
                $transaction_dates[337]['viewed'] ?? 'Not Found'  // Mini CME (337) Viewed
            ]);
        }
        fclose($handle);
    }
} else {
    // If the CSV file is not found or readable, output an error message
    fputcsv($output, ['CSV file not found or is not readable.']);
}

// Close the database connection
$conn->close();
?>
