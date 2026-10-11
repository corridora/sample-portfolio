<table><thead><tr><th>Symbol</th><th>Shares</th><th>Asset type</th></tr></thead><tbody>
@foreach($holdings as $holding)<tr><td><strong>{{ $holding['symbol'] }}</strong><span class="asset-name">{{ ['DEMO'=>'Demo Industries','CLOUD'=>'Cloud Collective','TRACE'=>'Trace Research'][$holding['symbol']] }}</span></td><td>{{ $holding['shares'] }}</td><td>Fictional equity</td></tr>@endforeach
</tbody></table>
