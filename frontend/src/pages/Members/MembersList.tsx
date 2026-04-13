/**
 * Members list page with table, search, and filtering.
 */
import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import {
    Box,
    Button,
    Card,
    CardContent,
    TextField,
    Typography,
    Table,
    TableBody,
    TableCell,
    TableContainer,
    TableHead,
    TableRow,
    TablePagination,
    Chip,
    IconButton,
    InputAdornment,
} from '@mui/material';
import {
    Add as AddIcon,
    Search as SearchIcon,
    Edit as EditIcon,
    Delete as DeleteIcon,
    FaceRetouchingNatural as EnrollIcon,
} from '@mui/icons-material';
import { membersApi, Member } from '@/api/members';

export const MembersList: React.FC = () => {
    const navigate = useNavigate();
    const [page, setPage] = useState(0);
    const [rowsPerPage, setRowsPerPage] = useState(25);
    const [search, setSearch] = useState('');

    const { data, isLoading } = useQuery({
        queryKey: ['members', page, rowsPerPage, search],
        queryFn: () =>
            membersApi.getMembers({
                skip: page * rowsPerPage,
                limit: rowsPerPage,
                search: search || undefined,
            }),
    });

    const getStatusColor = (status: string) => {
        switch (status) {
            case 'active':
                return 'success';
            case 'inactive':
                return 'default';
            case 'suspended':
                return 'error';
            default:
                return 'default';
        }
    };

    return (
        <Box>
            <Box display="flex" justifyContent="space-between" alignItems="center" mb={3}>
                <Typography variant="h4">Members</Typography>
                <Button
                    variant="contained"
                    startIcon={<AddIcon />}
                    onClick={() => navigate('/members/new')}
                >
                    Add Member
                </Button>
            </Box>

            <Card>
                <CardContent>
                    <TextField
                        fullWidth
                        placeholder="Search members..."
                        value={search}
                        onChange={(e) => setSearch(e.target.value)}
                        InputProps={{
                            startAdornment: (
                                <InputAdornment position="start">
                                    <SearchIcon />
                                </InputAdornment>
                            ),
                        }}
                        sx={{ mb: 2 }}
                    />

                    <TableContainer>
                        <Table>
                            <TableHead>
                                <TableRow>
                                    <TableCell>Name</TableCell>
                                    <TableCell>Email</TableCell>
                                    <TableCell>Phone</TableCell>
                                    <TableCell>Status</TableCell>
                                    <TableCell>Enrolled</TableCell>
                                    <TableCell align="right">Actions</TableCell>
                                </TableRow>
                            </TableHead>
                            <TableBody>
                                {isLoading ? (
                                    <TableRow>
                                        <TableCell colSpan={6} align="center">
                                            Loading...
                                        </TableCell>
                                    </TableRow>
                                ) : data?.members.length === 0 ? (
                                    <TableRow>
                                        <TableCell colSpan={6} align="center">
                                            No members found
                                        </TableCell>
                                    </TableRow>
                                ) : (
                                    data?.members.map((member: Member) => (
                                        <TableRow key={member.id} hover>
                                            <TableCell>
                                                {member.first_name} {member.last_name}
                                            </TableCell>
                                            <TableCell>{member.email}</TableCell>
                                            <TableCell>{member.phone}</TableCell>
                                            <TableCell>
                                                <Chip
                                                    label={member.status}
                                                    color={getStatusColor(member.status)}
                                                    size="small"
                                                />
                                            </TableCell>
                                            <TableCell>
                                                <Chip
                                                    label={member.consent_given ? 'Yes' : 'No'}
                                                    color={member.consent_given ? 'success' : 'default'}
                                                    size="small"
                                                />
                                            </TableCell>
                                            <TableCell align="right">
                                                <IconButton
                                                    size="small"
                                                    onClick={() => navigate(`/members/${member.id}/enroll`)}
                                                    title="Enroll Biometric"
                                                >
                                                    <EnrollIcon />
                                                </IconButton>
                                                <IconButton
                                                    size="small"
                                                    onClick={() => navigate(`/members/${member.id}/edit`)}
                                                    title="Edit"
                                                >
                                                    <EditIcon />
                                                </IconButton>
                                                <IconButton size="small" title="Delete">
                                                    <DeleteIcon />
                                                </IconButton>
                                            </TableCell>
                                        </TableRow>
                                    ))
                                )}
                            </TableBody>
                        </Table>
                    </TableContainer>

                    <TablePagination
                        component="div"
                        count={data?.total || 0}
                        page={page}
                        onPageChange={(_, newPage) => setPage(newPage)}
                        rowsPerPage={rowsPerPage}
                        onRowsPerPageChange={(e) => {
                            setRowsPerPage(parseInt(e.target.value, 10));
                            setPage(0);
                        }}
                    />
                </CardContent>
            </Card>
        </Box>
    );
};
