<?php
ini_set('display_errors', 1);
ini_set('display_startup_errors', 1);
include '../../config/constants.php'; // Database connection use $conn

$brand_campaign_id = isset($_GET['brand_campaign_id']) ? $_GET['brand_campaign_id'] : '';

// Query to get count of Field_ID and Cumulative_Count for each region
$query = "SELECT Region, COUNT(Field_ID) as field_count, SUM(Cumulative_Count) as doctor_count FROM report_data_MHlvVeLT GROUP BY Region";
$result = mysqli_query($conn, $query);

$regionData = [];
while ($row = mysqli_fetch_assoc($result)) {
    $regionData[$row['Region']] = [
        'field_count' => $row['field_count'],
        'doctor_count' => $row['doctor_count'],
        'link_sent_count' => 0,
        'link_opened_count' => 0
    ];
}

// Query to get unique doctor_number count for collateral_id = 387 where comment is Collateral Shared
$query = "SELECT rd.Region, COUNT(DISTINCT ct.doctor_number) as link_sent_count 
          FROM $brand_campaign_id ct 
          JOIN report_data_MHlvVeLT rd ON ct.field_id = rd.Field_ID 
          WHERE ct.collateral_id = 387 AND (ct.comment = 'Collateral Shared' OR ct.comment IS NOT NULL) 
          GROUP BY rd.Region";
$result = mysqli_query($conn, $query);

while ($row = mysqli_fetch_assoc($result)) {
    if (isset($regionData[$row['Region']])) {
        $regionData[$row['Region']]['link_sent_count'] = $row['link_sent_count'];
    }
}

// Query to get unique doctor_number count for collateral_id = 387 where viewed = 1 and comment is Collateral Viewed
$query = "SELECT rd.Region, COUNT(DISTINCT ct.doctor_number) as link_opened_count 
          FROM $brand_campaign_id ct 
          JOIN report_data_MHlvVeLT rd ON ct.field_id = rd.Field_ID 
          WHERE ct.collateral_id = 387 AND ct.viewed = 1 AND ct.comment = 'Collateral Viewed' 
          GROUP BY rd.Region";
$result = mysqli_query($conn, $query);

while ($row = mysqli_fetch_assoc($result)) {
    if (isset($regionData[$row['Region']])) {
        $regionData[$row['Region']]['link_opened_count'] = $row['link_opened_count'];
    }
}
?>

<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Region Table</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
</head>
<body>
    <div class="container mt-5">
        <h2 class="text-center mb-4">Region Table</h2>
        <table class="table table-bordered table-striped text-center">
            <thead class="table-dark">
                <tr>
                    <th>Region</th>
                    <th>No of Field ID</th>
                    <th>NO OF DOCTORS Registered</th>
                    <th>NO OF DOCTORS WHOM LINK WAS SENT</th>
                    <th>NO OF DOCTORS WHO OPENED THE LINK</th>
                </tr>
            </thead>
            <tbody>
                <?php
                $regions = ["TAMIL NADU", "PONDICHERRY", "KERALA", "KARNATAKA", "AP", "TG", "MAHARASHTRA", "GOA", "WEST BENGAL"];
                foreach ($regions as $region) {
                    $fieldCount = isset($regionData[$region]['field_count']) ? $regionData[$region]['field_count'] : 0;
                    $doctorCount = isset($regionData[$region]['doctor_count']) ? $regionData[$region]['doctor_count'] : 0;
                    $linkSentCount = isset($regionData[$region]['link_sent_count']) ? $regionData[$region]['link_sent_count'] : 0;
                    $linkOpenedCount = isset($regionData[$region]['link_opened_count']) ? $regionData[$region]['link_opened_count'] : 0;
                    echo "<tr><td>{$region}</td><td>{$fieldCount}</td><td>{$doctorCount}</td><td>{$linkSentCount}</td><td>{$linkOpenedCount}</td></tr>";
                }
                ?>
            </tbody>
        </table>
    </div>
    <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/js/bootstrap.bundle.min.js"></script>
</body>
</html>