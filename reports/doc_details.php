<?php
// error_reporting(E_ALL);
// ini_set('display_errors', 1);

require 'config/constants.php'; // Ensure your database connection path is correct

if ($_SERVER['REQUEST_METHOD'] === 'POST' && isset($_POST['doctor_numbers']) && isset($_POST['field_id'])) {
    $doctorNumbers = explode(',', $_POST['doctor_numbers']);
    $fieldId = $_POST['field_id'];

    function fetchDoctorDetails($conn, $doctorNumbers,$fieldId) {
        $doctorNumbersStr = implode(',', array_fill(0, count($doctorNumbers), '?'));
        $sql = "SELECT DISTINCT d.name AS doctor_name, d.mobile_number AS doctor_number, fr.field_id AS field_rep_id
            FROM doctors d
            JOIN field_reps fr ON d.field_unique_id = fr.unique_id AND fr.field_id = ?
            WHERE d.mobile_number IN ($doctorNumbersStr)";

    $stmt = $conn->prepare($sql);
    if (!$stmt) {
        die('MySQL prepare error: ' . $conn->error);
    }

    // Prepend the fieldId to the array of doctorNumbers for binding
    array_unshift($doctorNumbers, $fieldId);

    // Create a string for the bind_param function, 's' for each parameter
    $paramTypeString = str_repeat('s', count($doctorNumbers));

    // Bind the parameters to the statement
    $stmt->bind_param($paramTypeString, ...$doctorNumbers);
        $stmt->execute();
        $result = $stmt->get_result();

        $details = [];
        while ($row = $result->fetch_assoc()) {
            $details[] = $row;
        }
        return $details;
    }

    $doctorDetails = fetchDoctorDetails($conn, $doctorNumbers,$fieldId);
} else {
    die('Invalid request');
}
?>

<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Doctor Details</title>
    <style>
        @import url('https://fonts.googleapis.com/css2?family=Lexend:wght@300;400;500;600&display=swap');
        body {
            font-family: 'Lexend', sans-serif;
            margin: 0;
            padding: 20px;
            background-color: #f5f5f5;
        }
        table {
            width: 100%;
            margin-bottom: 20px;
            border-collapse: collapse;
            background-color: #fff;
            box-shadow: 0 0 10px rgba(0, 0, 0, 0.1);
        }
        table, th, td {
            border: 1px solid #ddd;
        }
        th, td {
            padding: 12px;
            text-align: left;
        }
        th {
            background-color: #f4f4f4;
        }
    </style>
</head>
<body>
    <center><h1>Doctor Details</h1></center>
    <table>
        <tr>
            <th>Doctor Name</th>
            <th>Doctor Number</th>
            <th>Field Rep ID</th>
        </tr>
        <?php foreach ($doctorDetails as $detail): ?>
            <tr>
                <td><?php echo htmlspecialchars($detail['doctor_name']); ?></td>
                <td><?php echo htmlspecialchars($detail['doctor_number']); ?></td>
                <td><?php echo htmlspecialchars($detail['field_rep_id']); ?></td>
            </tr>
        <?php endforeach; ?>
    </table>
</body>
</html>
