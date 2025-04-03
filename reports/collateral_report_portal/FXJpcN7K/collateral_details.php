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
            <tr>
                <td>272</td>
                <td>Mini CME Issue 1 on Managing High-Volume Pediatric Diarrhoea: Critical Insights for Healthcare Providers</td>
                <td><?php echo isset($collateralData[272]) ? $collateralData[272]['doctor_count'] : 0; ?></td>
                <td><?php echo isset($collateralData[272]) ? $collateralData[272]['doctor_click_count'] : 0; ?></td>
                <td><?php echo isset($collateralData[272]) ? $collateralData[272]['pdf_download'] : 0; ?></td>
                <td><?php echo isset($collateralData[272]) ? $collateralData[272]['pdf_last_page'] : 0; ?></td>
                <td>
                    <ul>
                        <li>Less than 50%: <?php echo isset($collateralData[272]) ? $collateralData[272]['video_less_50'] : 0; ?></li>
                        <li>More than 50%: <?php echo isset($collateralData[272]) ? $collateralData[272]['video_more_50'] : 0; ?></li>
                        <li>100%: <?php echo isset($collateralData[272]) ? $collateralData[272]['video_100'] : 0; ?></li>
                    </ul>
                </td>
            </tr>
            <!-- Repeat for other rows -->
            <tr>
                <td>273</td>
                <td>Mini CME Issue 2 on Understanding Diarrhoea and the Role of Antibiotics in Children</td>
                <td><?php echo isset($collateralData[273]) ? $collateralData[273]['doctor_count'] : 0; ?></td>
                <td><?php echo isset($collateralData[273]) ? $collateralData[273]['doctor_click_count'] : 0; ?></td>
                <td><?php echo isset($collateralData[273]) ? $collateralData[273]['pdf_download'] : 0; ?></td>
                <td><?php echo isset($collateralData[273]) ? $collateralData[273]['pdf_last_page'] : 0; ?></td>
                <td>
                    <ul>
                        <li>Less than 50%: <?php echo isset($collateralData[273]) ? $collateralData[273]['video_less_50'] : 0; ?></li>
                        <li>More than 50%: <?php echo isset($collateralData[273]) ? $collateralData[273]['video_more_50'] : 0; ?></li>
                        <li>100%: <?php echo isset($collateralData[273]) ? $collateralData[273]['video_100'] : 0; ?></li>
                    </ul>
                </td>
            </tr>
            <tr>
                <td>276</td>
                <td>Case Study Issue 1 on conditions linked to diarrhoea and nutrition</td>
                <td><?php echo isset($collateralData[276]) ? $collateralData[276]['doctor_count'] : 0; ?></td>
                <td><?php echo isset($collateralData[276]) ? $collateralData[276]['doctor_click_count'] : 0; ?></td>
                <td><?php echo isset($collateralData[276]) ? $collateralData[276]['pdf_download'] : 0; ?></td>
                <td><?php echo isset($collateralData[276]) ? $collateralData[276]['pdf_last_page'] : 0; ?></td>
                <td>
                    <ul>
                        <li>Less than 50%: <?php echo isset($collateralData[276]) ? $collateralData[276]['video_less_50'] : 0; ?></li>
                        <li>More than 50%: <?php echo isset($collateralData[276]) ? $collateralData[276]['video_more_50'] : 0; ?></li>
                        <li>100%: <?php echo isset($collateralData[276]) ? $collateralData[276]['video_100'] : 0; ?></li>
                    </ul>
                </td>
            </tr>
            <tr>
                <td>274</td>
                <td>Mini CME Issue 3 on Blood and Mucus in Pediatric Stools: Causes and Concern</td>
                <td><?php echo isset($collateralData[274]) ? $collateralData[274]['doctor_count'] : 0; ?></td>
                <td><?php echo isset($collateralData[274]) ? $collateralData[274]['doctor_click_count'] : 0; ?></td>
                <td><?php echo isset($collateralData[274]) ? $collateralData[274]['pdf_download'] : 0; ?></td>
                <td><?php echo isset($collateralData[274]) ? $collateralData[274]['pdf_last_page'] : 0; ?></td>
                <td>
                    <ul>
                        <li>Less than 50%: <?php echo isset($collateralData[274]) ? $collateralData[274]['video_less_50'] : 0; ?></li>
                        <li>More than 50%: <?php echo isset($collateralData[274]) ? $collateralData[274]['video_more_50'] : 0; ?></li>
                        <li>100%: <?php echo isset($collateralData[274]) ? $collateralData[274]['video_100'] : 0; ?></li>
                    </ul>
                </td>
            </tr>
            <tr>
                <td>275</td>
                <td>Mini CME Issue 4 on Fever in Pediatric Diarrhea: Infectious vs. Inflammatory Causes</td>
                <td><?php echo isset($collateralData[275]) ? $collateralData[275]['doctor_count'] : 0; ?></td>
                <td><?php echo isset($collateralData[275]) ? $collateralData[275]['doctor_click_count'] : 0; ?></td>
                <td><?php echo isset($collateralData[275]) ? $collateralData[275]['pdf_download'] : 0; ?></td>
                <td><?php echo isset($collateralData[275]) ? $collateralData[275]['pdf_last_page'] : 0; ?></td>
                <td>
                    <ul>
                        <li>Less than 50%: <?php echo isset($collateralData[275]) ? $collateralData[275]['video_less_50'] : 0; ?></li>
                        <li>More than 50%: <?php echo isset($collateralData[275]) ? $collateralData[275]['video_more_50'] : 0; ?></li>
                        <li>100%: <?php echo isset($collateralData[275]) ? $collateralData[275]['video_100'] : 0; ?></li>
                    </ul>
                </td>
            </tr>
            <tr>
                <td>318</td>
                <td>Mini CME Issue 5 on Oral Rehydration Solutions in Practice - Optimizing Use in Pediatric Diarrhea</td>
                <td><?php echo isset($collateralData[318]) ? $collateralData[318]['doctor_count'] : 0; ?></td>
                <td><?php echo isset($collateralData[318]) ? $collateralData[318]['doctor_click_count'] : 0; ?></td>
                <td><?php echo isset($collateralData[318]) ? $collateralData[318]['pdf_download'] : 0; ?></td>
                <td><?php echo isset($collateralData[318]) ? $collateralData[318]['pdf_last_page'] : 0; ?></td>
                <td>
                    <ul>
                        <li>Less than 50%: <?php echo isset($collateralData[318]) ? $collateralData[318]['video_less_50'] : 0; ?></li>
                        <li>More than 50%: <?php echo isset($collateralData[318]) ? $collateralData[318]['video_more_50'] : 0; ?></li>
                        <li>100%: <?php echo isset($collateralData[318]) ? $collateralData[318]['video_100'] : 0; ?></li>
                    </ul>
                </td>
            </tr>
            <tr>
                <td>277</td>
                <td>Case Study Issue 2 on conditions related to diarrhoea & nutrition</td>
                <td><?php echo isset($collateralData[277]) ? $collateralData[277]['doctor_count'] : 0; ?></td>
                <td><?php echo isset($collateralData[277]) ? $collateralData[277]['doctor_click_count'] : 0; ?></td>
                <td><?php echo isset($collateralData[277]) ? $collateralData[277]['pdf_download'] : 0; ?></td>
                <td><?php echo isset($collateralData[277]) ? $collateralData[277]['pdf_last_page'] : 0; ?></td>
                <td>
                    <ul>
                        <li>Less than 50%: <?php echo isset($collateralData[277]) ? $collateralData[277]['video_less_50'] : 0; ?></li>
                        <li>More than 50%: <?php echo isset($collateralData[277]) ? $collateralData[277]['video_more_50'] : 0; ?></li>
                        <li>100%: <?php echo isset($collateralData[277]) ? $collateralData[277]['video_100'] : 0; ?></li>
                    </ul>
                </td>
            </tr>
            <tr>
                <td>278</td>
                <td>Case Study Issue 3 on conditions related to diarrhoea & nutrition</td>
                <td><?php echo isset($collateralData[278]) ? $collateralData[278]['doctor_count'] : 0; ?></td>
                <td><?php echo isset($collateralData[278]) ? $collateralData[278]['doctor_click_count'] : 0; ?></td>
                <td><?php echo isset($collateralData[278]) ? $collateralData[278]['pdf_download'] : 0; ?></td>
                <td><?php echo isset($collateralData[278]) ? $collateralData[278]['pdf_last_page'] : 0; ?></td>
                <td>
                    <ul>
                        <li>Less than 50%: <?php echo isset($collateralData[278]) ? $collateralData[278]['video_less_50'] : 0; ?></li>
                        <li>More than 50%: <?php echo isset($collateralData[278]) ? $collateralData[278]['video_more_50'] : 0; ?></li>
                        <li>100%: <?php echo isset($collateralData[278]) ? $collateralData[278]['video_100'] : 0; ?></li>
                    </ul>
                </td>
            </tr>
            
        </tbody>
    </table>
</div>
<!-- Bootstrap JS and dependencies -->
<script src="https://code.jquery.com/jquery-3.5.1.slim.min.js"></script>
<script src="https://cdn.jsdelivr.net/npm/@popperjs/core@2.9.2/dist/umd/popper.min.js"></script>
<script src="https://maxcdn.bootstrapcdn.com/bootstrap/4.5.2/js/bootstrap.min.js"></script>
</body>
</html>
