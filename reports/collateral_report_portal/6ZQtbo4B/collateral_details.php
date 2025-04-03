<?php
// Enable error reporting
ini_set('display_errors', 1);
ini_set('display_startup_errors', 1);
error_reporting(E_ALL);

include '../../config/constants.php';

$brand_campaign_id = isset($_GET['brand_campaign_id']) ? $_GET['brand_campaign_id'] : '';

// Query to get the collateral data with unique doctor counts, downloads, last page views, and video percentages
$sql = "
    SELECT 
        collateral_id, 
        COUNT(DISTINCT doctor_number) AS doctor_count,
        COUNT(DISTINCT CASE WHEN viewed = 1 THEN doctor_number END) AS doctor_click_count,
        COUNT(DISTINCT CASE WHEN pdf_download = 1 THEN doctor_number END) AS pdf_download,
        COUNT(DISTINCT CASE WHEN pdf_page = 1 THEN doctor_number END) AS pdf_last_page,
        COUNT(DISTINCT CASE WHEN video_pec = 1 THEN doctor_number END) AS video_less_50,
        COUNT(DISTINCT CASE WHEN video_pec = 2 THEN doctor_number END) AS video_more_50,
        COUNT(DISTINCT CASE WHEN video_pec = 3 THEN doctor_number END) AS video_100
    FROM 
        collateral_transactions 
    WHERE 
        Brand_Campaign_ID = '$brand_campaign_id'
    GROUP BY 
        collateral_id
";

$result = $conn->query($sql);
$collateralData = [];

if ($result->num_rows > 0) {
    while ($row = $result->fetch_assoc()) {
        $collateralData[$row['collateral_id']] = [
            'doctor_count' => $row['doctor_count'],
            'doctor_click_count' => $row['doctor_click_count'],
            'pdf_download' => $row['pdf_download'],
            'pdf_last_page' => $row['pdf_last_page'],
            'video_less_50' => $row['video_less_50'],
            'video_more_50' => $row['video_more_50'],
            'video_100' => $row['video_100'],
        ];
    }
}

$conn->close();
?>

<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Collateral Table</title>
    <!-- Bootstrap CSS -->
    <link href="https://maxcdn.bootstrapcdn.com/bootstrap/4.5.2/css/bootstrap.min.css" rel="stylesheet">
</head>
<body>
<div class="container mt-5">
    <h3 class="mb-4">Collateral Information</h3>
    <table class="table table-bordered table-hover">
        <thead class="thead-dark">
            <tr>
                <th>Collateral ID</th>
                <th>Collateral Name</th>
                <th>No of Doctors with whom the collateral is shared</th>
                <th>No of Doctors who have clicked on the link</th>
                <th>No of doctors who have downloaded the PDF</th>
                <th>Number of doctors who have viewed the last page of PDF</th>
                <th>View Duration Of the Video (In Percentage)</th>
            </tr>
        </thead>
        <tbody>
            <?php
            $collaterals = [
                300 => "Mini CME on Tired of being : Tired Fatigue, Poor Sleep, and Their Allergic Rhinitis Roots",
                343 => "Case Study - Postnasal Drip",
                347 => "Mini CME on The Itch Factor: Identifying Itchy Nose, Ears, or Throat as Allergic Rhinitis Signals",
                357 => "Case Study on Conditions linked to Watery, Red, or Itchy Eye",
                355 => "Mini CME Behind the Drip: Postnasal Drip as a Key Indicator of Allergic Rhinitis",
                385 => "Mini CME on Sinus Siege-The Link Between Frequent Sinus Infections and Allergic Rhinitis",
                389 => "Mini CME on Shadows of Allergies: Dark Circles Under the Eyes and Their Significance in Allergic Rhinitis",
                217 => "Mini CME on Sneezing Marathons: Deciphering Frequent Sneezing in Allergic Rhinitis",
                231 => "Mini CME on Breathing Through the Maze_ Navigating Nasal Congestion in Allergic Rhinitis",
                216 => "Mini CME on The Dripping Faucet : Understanding Runny Nose in Allergic Conditions",
                249 => "Case study on conditions linked to frequent sneezing",
                302 => "Case study on conditions linked to Nasal Congestion",
                317 => "Mini CME on Frequent Headaches and their Link to Allergic Rhinitis",
                321 => "Case study on Conditions linked to Runny Nose",
                331 => "Case study on Itchy, Nose, Ears and Throat",
                354 => "Case Study for Conditions linked to Frequent Headaches",
                394 => "Mini CME on Pressure Points : Ear Pressure or Fullness as Allergic Rhinitis Clues",
                448 => "Case Study on Fatigue and Poor Sleep"
            ];

            foreach ($collaterals as $id => $name) {
                echo "<tr>";
                echo "<td>{$id}</td>";
                echo "<td>{$name}</td>";
                echo "<td>" . (isset($collateralData[$id]) ? $collateralData[$id]['doctor_count'] : 0) . "</td>";
                echo "<td>" . (isset($collateralData[$id]) ? $collateralData[$id]['doctor_click_count'] : 0) . "</td>";
                echo "<td>" . (isset($collateralData[$id]) ? $collateralData[$id]['pdf_download'] : 0) . "</td>";
                echo "<td>" . (isset($collateralData[$id]) ? $collateralData[$id]['pdf_last_page'] : 0) . "</td>";
                echo "<td>
                    <ul>
                        <li>Less than 50%: " . (isset($collateralData[$id]) ? $collateralData[$id]['video_less_50'] : 0) . "</li>
                        <li>More than 50%: " . (isset($collateralData[$id]) ? $collateralData[$id]['video_more_50'] : 0) . "</li>
                        <li>100%: " . (isset($collateralData[$id]) ? $collateralData[$id]['video_100'] : 0) . "</li>
                    </ul>
                </td>";
                echo "</tr>";
            }
            ?>
        </tbody>
    </table>
</div>
<!-- Bootstrap JS and dependencies -->
<script src="https://code.jquery.com/jquery-3.5.1.slim.min.js"></script>
<script src="https://cdn.jsdelivr.net/npm/@popperjs/core@2.9.2/dist/umd/popper.min.js"></script>
<script src="https://maxcdn.bootstrapcdn.com/bootstrap/4.5.2/js/bootstrap.min.js"></script>
</body>
</html>
