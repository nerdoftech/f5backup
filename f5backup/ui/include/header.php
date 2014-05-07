<?
// Internal web service connect
function webcheck () {
  //Connect to internal webservice
  $url = 'http://127.0.0.1:5380/api/v1.0/status';
  $curl = curl_init($url);
  curl_setopt($curl, CURLOPT_RETURNTRANSFER, true);
  curl_setopt($curl, CURLOPT_HTTPHEADER, array('Content-Type: application/json')); 
  json_decode(curl_exec($curl), true);

  //Did any curl errors occur ?
  if (curl_errno($curl)) {
    $error_msg = curl_error($curl);;
    return '<img style="vertical-align: middle;" src="/images/red_button.png"> Status: OFFLINE';
  };

  // Did server return an error ?
  $rtn_code = curl_getinfo($curl,CURLINFO_HTTP_CODE);
  if ( $rtn_code != 200 ) {
    $error_msg = '';
    return '<img style="vertical-align: middle;" src="/images/yellow_button.png"> Status: ERROR';
  };
  
return '<img style="vertical-align: middle;" src="/images/green_button.png"> Status: ONLINE';
  
};
?>

<html>
<head>
<link rel="stylesheet" type="text/css" href="css/style.css">
</head>
<body>
<table class="main">
<tr> <!-- Page Header ------------>
	<td class="header" colspan="2">
		<div id="title"><a href="/">Config Backup for F5</a></div>
		<div id="logout"><a href="logout.php">Log out</a></div>
		<div id="status"><?= webcheck()?></div>
		<div id="user">Username: <?= $_SESSION['user'] ?></div>
		<div id="ip">User IP: <?= $_SERVER['REMOTE_ADDR'] ?></div>
		<div id="date">Date: <?= date('Y-m-d',time()) ?></div>
		<div id="time">Time: <?= date('H:i',time()) ?></div>
	</td>
</tr>


