<?php
ini_set('display_errors', 1);
ini_set('display_startup_errors', 1);
include '../../config/constants.php';

$brand_campaign_id = isset($_GET['brand_campaign_id']) ? $_GET['brand_campaign_id'] : '';

// Path to the CSV file
$csvFile = 'Report.csv';

// Initialize an empty array to store CSV data
$data = [];

// Open the CSV file for reading
if (($handle = fopen($csvFile, "r")) !== FALSE) {
    // Read the headers
    $headers = fgetcsv($handle);

    // Read the file line by line
    while (($row = fgetcsv($handle)) !== FALSE) {
        // Combine the row data with the headers to create an associative array
        $data[] = array_combine($headers, $row);
    }

    // Close the file handle
    fclose($handle);
}

// Fetch the data from the database
$fieldData = [];
if ($conn) {
    $query = "
        SELECT field_id, COUNT(DISTINCT doctor_number) AS doctor_count, 
        COUNT(DISTINCT CASE WHEN viewed = 1 THEN doctor_number END) AS viewed_count
        FROM collateral_transactions
        WHERE collateral_id = 382
        GROUP BY field_id";

    $result = $conn->query($query);
    if ($result && $result->num_rows > 0) {
        while ($row = $result->fetch_assoc()) {
            $fieldData[$row['field_id']] = [
                'doctor_count' => $row['doctor_count'],
                'viewed_count' => $row['viewed_count']
            ];
        }
    }
    $conn->close();
}
?>

<!DOCTYPE html>
<html lang="en">

<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Field ID Data</title>
    <link href="https://stackpath.bootstrapcdn.com/bootstrap/4.5.2/css/bootstrap.min.css" rel="stylesheet">
    <style>
        .btn-container {
            display: flex;
            justify-content: start;
            gap: 10px;
            margin-bottom: 20px;
        }
    </style>
</head>

<body>
    <div class="container mt-5">
        <h2 class="mb-4">Field ID Data</h2>
        <table class="table table-bordered">
            <thead class="thead-dark">
                <tr>
                    <th scope="col">Field ID</th>
                    <th scope="col">No. of doctors Mini CME on Management of Upper Respiratory Tract Infections in Children Collateral shared with</th>
                    <th scope="col">No. of doctors who viewed Mini CME on Management of Upper Respiratory Tract Infections in Children Collateral</th>
                </tr>
            </thead>
            <tbody>
                <?php if (!empty($data)): ?>
                    <?php foreach ($data as $row): ?>
                        <tr>
                            <td><?= htmlspecialchars($row['Field ID']) ?></td>
                            <td><?= isset($fieldData[$row['Field ID']]) ? $fieldData[$row['Field ID']]['doctor_count'] : 0 ?></td>
                            <td><?= isset($fieldData[$row['Field ID']]) ? $fieldData[$row['Field ID']]['viewed_count'] : 0 ?></td>
                        </tr>
                    <?php endforeach; ?>
                <?php else: ?>
                    <tr>
                        <td colspan="3" class="text-center">No data available</td>
                    </tr>
                <?php endif; ?>
            </tbody>
        </table>
    </div>

    <script src="https://code.jquery.com/jquery-3.5.1.slim.min.js"></script>
    <script src="https://cdn.jsdelivr.net/npm/@popperjs/core@2.9.2/dist/umd/popper.min.js"></script>
    <script src="https://stackpath.bootstrapcdn.com/bootstrap/4.5.2/js/bootstrap.min.js"></script>
</body>

</html>