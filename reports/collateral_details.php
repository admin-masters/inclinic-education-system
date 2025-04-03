<?php
error_reporting(E_ALL);
ini_set('display_errors', 1);
require 'config/constants.php'; // connection file
// Fetching the brand_campaign_id from the URL

$brand_campaign_id = isset($_GET['brand_campaign_id']) ? $_GET['brand_campaign_id'] : '';

// Query to fetch all doctors with duplicate mobile numbers within the same brand_campaign_id
$sql = "
    SELECT d1.id, d1.name, d1.mobile_number, d1.field_unique_id, d1.field_id, d1.Brand_Campaign_ID
    FROM doctors d1
    INNER JOIN (
        SELECT mobile_number, COUNT(*) as count
        FROM doctors
        WHERE Brand_Campaign_ID = ?
        GROUP BY mobile_number
        HAVING count > 1
    ) d2 ON d1.mobile_number = d2.mobile_number
    WHERE d1.Brand_Campaign_ID = ?
    ORDER BY d1.mobile_number, d1.id ASC";
$stmt = $conn->prepare($sql);
$stmt->bind_param("ss", $brand_campaign_id, $brand_campaign_id);
$stmt->execute();
$result = $stmt->get_result();

$doctors = [];
if ($result->num_rows > 0) {
    while ($row = $result->fetch_assoc()) {
        $doctors[] = $row;
    }
} else {
    echo "No duplicate doctors found for the given Brand Campaign ID.";
}

$stmt->close();
$conn->close();
?>

<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Duplicate Doctors Details</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
    <style>
        .table-custom {
            margin: 20px auto;
            width: 75%;
        }
        .table-custom th, .table-custom td {
            text-align: center;
            vertical-align: middle;
        }
        .table-custom th {
            background-color: #f8f9fa;
            font-weight: bold;
        }
        .table-custom td {
            background-color: #ffffff;
        }
    </style>
</head>
<body>
    <div class="container">
        <h2 class="text-center mt-5">Duplicate Doctors Details</h2>
        
        <?php if (!empty($doctors)) { ?>
            <table class="table table-bordered table-custom">
                <thead>
                    <tr>
                        <th>ID</th>
                        <th>Name</th>
                        <th>Mobile Number</th>
                        <th>Field Unique ID</th>
                        <th>Field ID</th>
                        <th>Brand Campaign ID</th>
                    </tr>
                </thead>
                <tbody>
                    <?php foreach ($doctors as $doctor) { ?>
                        <tr>
                            <td><?php echo htmlspecialchars($doctor['id']); ?></td>
                            <td><?php echo htmlspecialchars($doctor['name']); ?></td>
                            <td><?php echo htmlspecialchars($doctor['mobile_number']); ?></td>
                            <td><?php echo htmlspecialchars($doctor['field_unique_id']); ?></td>
                            <td><?php echo htmlspecialchars($doctor['field_id']); ?></td>
                            <td><?php echo htmlspecialchars($doctor['Brand_Campaign_ID']); ?></td>
                        </tr>
                    <?php } ?>
                </tbody>
            </table>
        <?php } else { ?>
            <p class="text-center mt-5">No duplicate doctors found for the provided criteria.</p>
        <?php } ?>
    </div>
    
    <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/js/bootstrap.bundle.min.js"></script>
</body>
</html>
