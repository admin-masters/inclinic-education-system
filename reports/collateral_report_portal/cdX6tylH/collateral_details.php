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
                <td>218</td>
                <td>Mini CME on Evaluating Stunted Growth</td>
                <td><?php echo isset($collateralData[218]) ? $collateralData[218]['doctor_count'] : 0; ?></td>
                <td><?php echo isset($collateralData[218]) ? $collateralData[218]['doctor_click_count'] : 0; ?></td>
                <td><?php echo isset($collateralData[218]) ? $collateralData[218]['pdf_download'] : 0; ?></td>
                <td><?php echo isset($collateralData[218]) ? $collateralData[218]['pdf_last_page'] : 0; ?></td>
                <td>
                    <ul>
                        <li>Less than 50%: <?php echo isset($collateralData[218]) ? $collateralData[218]['video_less_50'] : 0; ?></li>
                        <li>More than 50%: <?php echo isset($collateralData[218]) ? $collateralData[218]['video_more_50'] : 0; ?></li>
                        <li>100%: <?php echo isset($collateralData[218]) ? $collateralData[218]['video_100'] : 0; ?></li>
                    </ul>
                </td>
            </tr>
            <!-- Repeat for other rows -->
            <tr>
                <td>219</td>
                <td>Mini CME on Gastrointestinal Red Flags in Children : Especially for children 6-14 years</td>
                <td><?php echo isset($collateralData[219]) ? $collateralData[219]['doctor_count'] : 0; ?></td>
                <td><?php echo isset($collateralData[219]) ? $collateralData[219]['doctor_click_count'] : 0; ?></td>
                <td><?php echo isset($collateralData[219]) ? $collateralData[219]['pdf_download'] : 0; ?></td>
                <td><?php echo isset($collateralData[219]) ? $collateralData[219]['pdf_last_page'] : 0; ?></td>
                <td>
                    <ul>
                        <li>Less than 50%: <?php echo isset($collateralData[219]) ? $collateralData[219]['video_less_50'] : 0; ?></li>
                        <li>More than 50%: <?php echo isset($collateralData[219]) ? $collateralData[219]['video_more_50'] : 0; ?></li>
                        <li>100%: <?php echo isset($collateralData[219]) ? $collateralData[219]['video_100'] : 0; ?></li>
                    </ul>
                </td>
            </tr>
            <tr>
                <td>242</td>
                <td>Mini CME on The Risks of Avoiding Food Groups in Pediatric Diets</td>
                <td><?php echo isset($collateralData[242]) ? $collateralData[242]['doctor_count'] : 0; ?></td>
                <td><?php echo isset($collateralData[242]) ? $collateralData[242]['doctor_click_count'] : 0; ?></td>
                <td><?php echo isset($collateralData[242]) ? $collateralData[242]['pdf_download'] : 0; ?></td>
                <td><?php echo isset($collateralData[242]) ? $collateralData[242]['pdf_last_page'] : 0; ?></td>
                <td>
                    <ul>
                        <li>Less than 50%: <?php echo isset($collateralData[242]) ? $collateralData[242]['video_less_50'] : 0; ?></li>
                        <li>More than 50%: <?php echo isset($collateralData[242]) ? $collateralData[242]['video_more_50'] : 0; ?></li>
                        <li>100%: <?php echo isset($collateralData[242]) ? $collateralData[242]['video_100'] : 0; ?></li>
                    </ul>
                </td>
            </tr>
            <tr>
                <td>243</td>
                <td>Mini CME on Nutrition and Immunity: A Comprehensive Guide</td>
                <td><?php echo isset($collateralData[243]) ? $collateralData[243]['doctor_count'] : 0; ?></td>
                <td><?php echo isset($collateralData[243]) ? $collateralData[243]['doctor_click_count'] : 0; ?></td>
                <td><?php echo isset($collateralData[243]) ? $collateralData[243]['pdf_download'] : 0; ?></td>
                <td><?php echo isset($collateralData[243]) ? $collateralData[243]['pdf_last_page'] : 0; ?></td>
                <td>
                    <ul>
                        <li>Less than 50%: <?php echo isset($collateralData[243]) ? $collateralData[243]['video_less_50'] : 0; ?></li>
                        <li>More than 50%: <?php echo isset($collateralData[243]) ? $collateralData[243]['video_more_50'] : 0; ?></li>
                        <li>100%: <?php echo isset($collateralData[243]) ? $collateralData[243]['video_100'] : 0; ?></li>
                    </ul>
                </td>
            </tr>
            <tr>
                <td>244</td>
                <td>Mini CME on Behavioral Changes in Children</td>
                <td><?php echo isset($collateralData[244]) ? $collateralData[244]['doctor_count'] : 0; ?></td>
                <td><?php echo isset($collateralData[244]) ? $collateralData[244]['doctor_click_count'] : 0; ?></td>
                <td><?php echo isset($collateralData[244]) ? $collateralData[244]['pdf_download'] : 0; ?></td>
                <td><?php echo isset($collateralData[244]) ? $collateralData[244]['pdf_last_page'] : 0; ?></td>
                <td>
                    <ul>
                        <li>Less than 50%: <?php echo isset($collateralData[244]) ? $collateralData[244]['video_less_50'] : 0; ?></li>
                        <li>More than 50%: <?php echo isset($collateralData[244]) ? $collateralData[244]['video_more_50'] : 0; ?></li>
                        <li>100%: <?php echo isset($collateralData[244]) ? $collateralData[244]['video_100'] : 0; ?></li>
                    </ul>
                </td>
            </tr>
            <tr>
                <td>262</td>
                <td>Mini CME on Addressing Limited Diet Variety in Children: Strategies for General Physicians</td>
                <td><?php echo isset($collateralData[262]) ? $collateralData[262]['doctor_count'] : 0; ?></td>
                <td><?php echo isset($collateralData[262]) ? $collateralData[262]['doctor_click_count'] : 0; ?></td>
                <td><?php echo isset($collateralData[262]) ? $collateralData[262]['pdf_download'] : 0; ?></td>
                <td><?php echo isset($collateralData[262]) ? $collateralData[262]['pdf_last_page'] : 0; ?></td>
                <td>
                    <ul>
                        <li>Less than 50%: <?php echo isset($collateralData[262]) ? $collateralData[262]['video_less_50'] : 0; ?></li>
                        <li>More than 50%: <?php echo isset($collateralData[262]) ? $collateralData[262]['video_more_50'] : 0; ?></li>
                        <li>100%: <?php echo isset($collateralData[262]) ? $collateralData[262]['video_100'] : 0; ?></li>
                    </ul>
                </td>
            </tr>
            <tr>
                <td>263</td>
                <td>Mini CME on Processed Foods and Pediatric Health</td>
                <td><?php echo isset($collateralData[263]) ? $collateralData[263]['doctor_count'] : 0; ?></td>
                <td><?php echo isset($collateralData[263]) ? $collateralData[263]['doctor_click_count'] : 0; ?></td>
                <td><?php echo isset($collateralData[263]) ? $collateralData[263]['pdf_download'] : 0; ?></td>
                <td><?php echo isset($collateralData[263]) ? $collateralData[263]['pdf_last_page'] : 0; ?></td>
                <td>
                    <ul>
                        <li>Less than 50%: <?php echo isset($collateralData[263]) ? $collateralData[263]['video_less_50'] : 0; ?></li>
                        <li>More than 50%: <?php echo isset($collateralData[263]) ? $collateralData[263]['video_more_50'] : 0; ?></li>
                        <li>100%: <?php echo isset($collateralData[263]) ? $collateralData[263]['video_100'] : 0; ?></li>
                    </ul>
                </td>
            </tr>
            <tr>
                <td>367</td>
                <td>Mini CME- Identifying and Addressing Unusual Weight Changes in Children</td>
                <td><?php echo isset($collateralData[367]) ? $collateralData[367]['doctor_count'] : 0; ?></td>
                <td><?php echo isset($collateralData[367]) ? $collateralData[367]['doctor_click_count'] : 0; ?></td>
                <td><?php echo isset($collateralData[367]) ? $collateralData[367]['pdf_download'] : 0; ?></td>
                <td><?php echo isset($collateralData[367]) ? $collateralData[367]['pdf_last_page'] : 0; ?></td>
                <td>
                    <ul>
                        <li>Less than 50%: <?php echo isset($collateralData[367]) ? $collateralData[367]['video_less_50'] : 0; ?></li>
                        <li>More than 50%: <?php echo isset($collateralData[367]) ? $collateralData[367]['video_more_50'] : 0; ?></li>
                        <li>100%: <?php echo isset($collateralData[367]) ? $collateralData[367]['video_100'] : 0; ?></li>
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
