<?php
ini_set('display_errors', 1);
ini_set('display_startup_errors', 1);
error_reporting(E_ALL);

include "config/constants.php";
include "config/forms_db.php";  // CICDB connection
include "config/product_db.php"; // Product DB connection

$type = $_GET['type'];
$timeframe = $_GET['timeframe'];
$date = $_GET['date'];

$date_time = new DateTime($date);

// Convert to start and end date for the last 24 hours
$start_date_24h = $date_time->format('Y-m-d 00:00:00');
$end_date_24h = (new DateTime($date))->modify('+1 day')->format('Y-m-d 00:00:00');

$names = [];

// Function to query the CICDB (CIC connection for doctor_recruitment, url_whatsapp, etc.)
function queryCICDB($sql) {
    global $conn;
    $result = $conn->query($sql);
    if (!$result) {
        throw new Exception("CICDB Database Error [{$conn->errno}] {$conn->error}");
    }
    return $result;
}

// Function to query the Product DB (product_conn for mha and patient_reports)
function queryProduct($sql) {
    global $product_conn;
    $result = $product_conn->query($sql);
    if (!$result) {
        throw new Exception("Product Database Error [{$product_conn->errno}] {$product_conn->error}");
    }
    return $result;
}

function queryScreeningAppDB($sql) {
    global $form_db;
    $result = $form_db->query($sql);
    if (!$result) {
        throw new Exception("Database Error [{$form_db->errno}] {$form_db->error}");
    }
    return $result;
}

try {
    if (in_array($type, ['free_doctors', 'free_caregivers'])) {
        if ($timeframe == '24h') {
            $sql = "SELECT DISTINCT doctor_id FROM url_whatsapp WHERE DATE(created_at) = '$date'";
        } else {
            $sql = "SELECT DISTINCT doctor_id FROM url_whatsapp WHERE created_at <= '$end_date_24h'";
        }
        
        $result = queryScreeningAppDB($sql);
        $doctor_ids = [];
        
        while ($row = $result->fetch_assoc()) {
            $doctor_ids[] = $row['doctor_id'];
        }
        
        if (!empty($doctor_ids)) {
            // Use the connection object's real_escape_string method
            $escaped_ids = array_map(function($id) use ($conn) {
                return $conn->real_escape_string($id);
            }, $doctor_ids);
            
            $doctor_ids_list = implode("','", $escaped_ids);
            
            if ($type == 'free_doctors') {
                $sql = "
                    SELECT pr.form_title, pr.patient_name, pr.patient_number 
                    FROM patient_reports pr
                    JOIN doctor_recruitment dr ON dr.doctor_code = pr.doctor_id
                    WHERE pr.form_title LIKE '%Behavioral%' AND dr.doctor_code IN ('$doctor_ids_list')
                ";
            } elseif ($type == 'free_caregivers') {
                $sql = "
                    SELECT pr.form_title, pr.patient_name, pr.patient_number 
                    FROM patient_reports pr
                    JOIN doctor_recruitment dr ON dr.doctor_code = pr.doctor_id
                    WHERE pr.form_title LIKE '%Behavioral%' AND dr.doctor_code IN ('$doctor_ids_list')
                ";
            }
            
            // Query Product DB for free doctors and caregivers
            $result = queryProduct($sql);
        }
    } else {
        if ($type == 'paid_doctors' && $timeframe == '24h') {
            $sql = "
                SELECT dr.doctor_name, dr.doctor_number, m.form_id, m.patientName, m.patientNumber
                FROM doctor_recruitment dr
                JOIN mha m ON m.doctor_id = dr.doctor_code
                WHERE dr.doctor_type='Doctor' AND dr.doctor_name NOT LIKE 'Inditech%' 
                AND m.date BETWEEN '$start_date_24h' AND '$end_date_24h'
            ";
        } elseif ($type == 'paid_doctors' && $timeframe == 'cumulative') {
            $sql = "
                SELECT dr.doctor_name, dr.doctor_number, m.form_id, m.patientName, m.patientNumber
                FROM doctor_recruitment dr
                JOIN mha m ON m.doctor_id = dr.doctor_code
                WHERE dr.doctor_type='Doctor' AND dr.doctor_name NOT LIKE 'Inditech%' 
                AND m.date <= '$end_date_24h'
            ";
        } elseif ($type == 'paid_caregivers' && $timeframe == '24h') {
            $sql = "
                SELECT dr.doctor_name, dr.doctor_number, m.form_id, m.patientName, m.patientNumber
                FROM doctor_recruitment dr
                JOIN mha m ON m.doctor_id = dr.doctor_code
                WHERE dr.doctor_type='emo' AND dr.doctor_name NOT LIKE 'Inditech%' 
                AND m.date BETWEEN '$start_date_24h' AND '$end_date_24h'
            ";
        } elseif ($type == 'paid_caregivers' && $timeframe == 'cumulative') {
            $sql = "
                SELECT dr.doctor_name, dr.doctor_number, m.form_id, m.patientName, m.patientNumber
                FROM doctor_recruitment dr
                JOIN mha m ON m.doctor_id = dr.doctor_code
                WHERE dr.doctor_type='emo' AND dr.doctor_name NOT LIKE 'Inditech%' 
                AND m.date <= '$end_date_24h'
            ";
        }
        
        // Query Product DB for paid doctors and caregivers
        $result = queryProduct($sql);
    }
    
    while ($row = $result->fetch_assoc()) {
        $names[] = [
            'name' => $row['doctor_name'], 
            'number' => $row['doctor_number'],
            'form_name' => isset($row['form_id']) ? $row['form_id'] : $row['form_title'],  // Form name
            'patient_name' => $row['patientName'] ?? $row['patient_name'],  // Patient Name
            'patient_number' => $row['patientNumber'] ?? $row['patient_number']  // Patient Number
        ];
    }
} catch (Exception $e) {
    echo "Error: " . $e->getMessage();
}
?>

<!DOCTYPE html>
<html>
<head>
    <title>Doctor Names</title>
    <style>
        body {
            font-family: Arial, sans-serif;
        }
        .name-list {
            width: 80%;
            margin: 20px auto;
            border-collapse: collapse;
        }
        .name-list th, .name-list td {
            border: 1px solid #ddd;
            padding: 8px;
            text-align: center;
        }
        .name-list th {
            background-color: #f2f2f2;
            font-weight: bold;
        }
    </style>
</head>
<body>
    <h2><?php echo ucfirst(str_replace('_', ' ', $type)) . " (" . ($timeframe == '24h' ? "Last 24 hours" : "Cumulative") . ")"; ?></h2>
    <table class="name-list">
        <tr>
            <th>Name</th>
            <th>Number</th>
            <th>Form Name</th>
            <th>Patient Name</th>
            <th>Patient Number</th>
        </tr>
        <?php foreach ($names as $entry): ?>
        <tr>
            <td><?php echo htmlspecialchars($entry['name']); ?></td>
            <td><?php echo htmlspecialchars($entry['number']); ?></td>
            <td><?php echo htmlspecialchars($entry['form_name']); ?></td>
            <td><?php echo htmlspecialchars($entry['patient_name']); ?></td>
            <td><?php echo htmlspecialchars($entry['patient_number']); ?></td>
        </tr>
        <?php endforeach; ?>
    </table>
</body>
</html>
