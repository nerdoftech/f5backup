<?
session_start();
if(!(isset( $_SESSION['active']))) {
//If user does not have active session then logout user
	$location = "https://".$_SERVER['HTTP_HOST']."/login.php?page=".urlencode($_SERVER['REQUEST_URI']);
	header("Location: $location");
	die();
} elseif ( $_SESSION['clientip'] != $_SERVER['REMOTE_ADDR'] ) {
// If users IP has changed
	header("Location: /logout.php");
} else {
// Check if the user is timed out
	if ( (time() - $_SESSION['time']) > $_SESSION['timeout'] ) { 
	// If current time - session time is > timeout, logout user	
		header("Location: /logout.php"); 
	} else {
	// If not reset session time
		$_SESSION['time'] = time();
	};
};
date_default_timezone_set(@date_default_timezone_get());
?>
